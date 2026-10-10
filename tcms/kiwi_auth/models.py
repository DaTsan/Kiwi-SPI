# -*- coding: utf-8 -*-

import datetime
import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserActivationKey(models.Model):
    class Meta:
        verbose_name = _("User activation key")
        verbose_name_plural = _("User activation keys")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("User"), on_delete=models.CASCADE
    )
    activation_key = models.CharField(
        verbose_name=_("Activation key"), max_length=64, null=True, blank=True
    )
    key_expires = models.DateTimeField(
        verbose_name=_("Key expires"), null=True, blank=True
    )

    @classmethod
    def set_random_key_for_user(cls, user, force=False):
        activation_key = secrets.token_hex()

        # Create and save their profile
        user_activation_key, created = cls.objects.get_or_create(user=user)
        if created or force:
            user_activation_key.activation_key = activation_key
            user_activation_key.key_expires = (
                datetime.datetime.today() + datetime.timedelta(7)
            )
            user_activation_key.save()

        return user_activation_key
