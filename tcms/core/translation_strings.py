"""Built-in database labels used by vinaigrette, included in gettext extraction.

The database stores the original values; translated labels never replace keys.
"""

from django.utils.translation import gettext_noop

DJANGO_WIDGET_LABELS = (gettext_noop("- Select an option -"),)

DEFAULT_STATUS_LABELS = (
    gettext_noop("PROPOSED"),
    gettext_noop("CONFIRMED"),
    gettext_noop("DISABLED"),
    gettext_noop("NEED_UPDATE"),
    gettext_noop("IDLE"),
    gettext_noop("RUNNING"),
    gettext_noop("PAUSED"),
    gettext_noop("PASSED"),
    gettext_noop("FAILED"),
    gettext_noop("BLOCKED"),
    gettext_noop("ERROR"),
    gettext_noop("WAIVED"),
)
