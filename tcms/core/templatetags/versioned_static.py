"""Keep browser assets in sync with the deployed application."""

import hashlib
from urllib.parse import urlsplit, urlunsplit

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def versioned_static(name):
    """Change the asset URL when its contents change, including in DEBUG mode."""
    url = static(name)
    filename = finders.find(name)
    if not filename:
        try:
            filename = staticfiles_storage.path(name)
        except NotImplementedError:
            return url
    try:
        with open(filename, "rb") as asset:
            version = hashlib.file_digest(asset, "sha256").hexdigest()[:16]
    except FileNotFoundError:
        return url

    parts = urlsplit(url)
    query = f"{parts.query}&v={version}" if parts.query else f"v={version}"
    return urlunsplit(parts._replace(query=query))
