"""A normal page reload must pick up a newly deployed JavaScript bundle."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.template import Context, Template
from django.test import SimpleTestCase

from tcms.core.templatetags.versioned_static import versioned_static


class VersionedStaticTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bundle = Path(self.directory.name) / "js" / "bundle.js"
        self.bundle.parent.mkdir()
        self.bundle.write_bytes(b"old bundle")
        settings = self.settings(
            STATIC_URL="/static/",
            STATIC_ROOT=str(Path(self.directory.name) / "collected"),
            STATICFILES_DIRS=[self.directory.name],
            STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"],
            STORAGES={
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                }
            },
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def test_unchanged_bundle_keeps_url(self):
        url = versioned_static("js/bundle.js")
        self.assertRegex(url, r"^/static/js/bundle\.js\?v=[0-9a-f]{16}$")
        self.assertEqual(versioned_static("js/bundle.js"), url)

    def test_rebuilt_bundle_changes_url_even_with_same_file_size(self):
        previous = versioned_static("js/bundle.js")
        self.bundle.write_bytes(b"new bundle")
        self.assertNotEqual(versioned_static("js/bundle.js"), previous)

    def test_collected_bundle_works_without_source_directory(self):
        with self.settings(STATIC_ROOT=self.directory.name, STATICFILES_DIRS=[]):
            self.assertIn("?v=", versioned_static("js/bundle.js"))

    def test_missing_bundle_keeps_standard_static_url(self):
        self.bundle.unlink()
        self.assertEqual(versioned_static("js/bundle.js"), "/static/js/bundle.js")

    def test_preserves_existing_query_and_fragment(self):
        with patch(
            "tcms.core.templatetags.versioned_static.static",
            return_value="https://assets.example/bundle.js?token=public#fragment",
        ):
            self.assertRegex(
                versioned_static("js/bundle.js"),
                r"^https://assets\.example/bundle\.js\?token=public&v=[0-9a-f]{16}#fragment$",
            )

    def test_template_loads_current_version(self):
        template = Template(
            "{% load versioned_static %}{% versioned_static 'js/bundle.js' %}"
        )
        previous = template.render(Context())
        self.bundle.write_bytes(b"new bundle")
        self.assertNotEqual(template.render(Context()), previous)
