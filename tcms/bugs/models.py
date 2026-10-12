# Copyright (c) 2019-2022 Alexander Todorov <atodorov@MrSenko.com>

# Licensed under the GPL 2.0: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html

from colorfield.fields import ColorField
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from tcms.core.models.base import UrlMixin


class Severity(models.Model):
    name = models.CharField(verbose_name=_("Name"), max_length=64, unique=True)
    weight = models.IntegerField(verbose_name=_("Weight"), default=0)
    icon = models.CharField(verbose_name=_("Icon"), max_length=64)
    color = ColorField(verbose_name=_("Color"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Severity")
        verbose_name_plural = _("Severity")


class Bug(models.Model, UrlMixin):
    summary = models.CharField(verbose_name=_("Summary"), max_length=255, db_index=True)
    created_at = models.DateTimeField(
        verbose_name=_("Created at"), auto_now_add=True, db_index=True
    )
    # True means bug is still open
    status = models.BooleanField(verbose_name=_("Status"), default=True, db_index=True)

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Reporter"),
        on_delete=models.CASCADE,
        related_name="repoted_bugs",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Assignee"),
        on_delete=models.CASCADE,
        related_name="assigned_bugs",
        null=True,
        blank=True,
    )

    product = models.ForeignKey(
        "management.Product", verbose_name=_("Product"), on_delete=models.CASCADE
    )
    version = models.ForeignKey(
        "management.Version", verbose_name=_("Version"), on_delete=models.CASCADE
    )
    build = models.ForeignKey(
        "management.Build", verbose_name=_("Build"), on_delete=models.CASCADE
    )
    severity = models.ForeignKey(
        Severity,
        verbose_name=_("Severity"),
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    executions = models.ManyToManyField(
        "testruns.TestExecution", verbose_name=_("Executions"), related_name="bugs"
    )
    tags = models.ManyToManyField(
        "management.Tag", verbose_name=_("Tags"), related_name="bugs"
    )

    def __str__(self):
        return f"BUG-{self.pk}: {self.summary} "

    def _get_absolute_url(self):
        return reverse(
            "bugs-get",
            args=[
                self.pk,
            ],
        )

    def get_absolute_url(self):
        return self._get_absolute_url()

    class Meta:
        verbose_name = _("Bug")
        verbose_name_plural = _("Bugs")
