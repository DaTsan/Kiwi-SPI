from django.db import models
from django.utils.translation import gettext_lazy as _


class Property(models.Model):
    name = models.CharField(verbose_name=_("Name"), max_length=255)
    value = models.CharField(verbose_name=_("Value"), max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name}: {self.value}"
