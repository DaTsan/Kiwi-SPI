from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ManagementConfig(AppConfig):
    name = "tcms.management"
    verbose_name = _("Product management")
