from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkflowConfig(AppConfig):
    name = "tcms.workflow"
    verbose_name = _("Planning and execution")

    def ready(self):
        from django.db.models.signals import post_save

        from tcms.testruns.models import TestExecution

        from .signals import capture_execution

        post_save.connect(
            capture_execution,
            sender=TestExecution,
            dispatch_uid="workflow.capture_execution",
        )
