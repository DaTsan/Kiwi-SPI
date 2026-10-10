from django import template
from django.utils.translation import gettext

register = template.Library()


@register.filter
def display_value(value):
    """Translate boolean labels without altering user-entered text."""
    if value is True:
        return gettext("Yes")
    if value is False:
        return gettext("No")
    return value
