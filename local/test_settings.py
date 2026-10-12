"""Disposable-container tests: no connection to the running MariaDB."""

import tempfile

from tcms.settings.test import *  # noqa: F401,F403

LANGUAGE_CODE = "en-us"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = tempfile.mkdtemp(prefix="kiwi-test-uploads-")
STATIC_ROOT = tempfile.mkdtemp(prefix="kiwi-test-static-")
STATICFILES_DIRS = [
    str(TCMS_ROOT_PATH) + "/static",  # noqa: F405
    "/Kiwi/tcms/static",
    "/Kiwi/tcms/node_modules",
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
