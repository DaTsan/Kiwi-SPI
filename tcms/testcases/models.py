# -*- coding: utf-8 -*-
from datetime import timedelta

import vinaigrette
from django.conf import settings
from django.core.validators import URLValidator
from django.db import models
from django.db.models import ObjectDoesNotExist
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from tcms.core.history import KiwiHistoricalRecords
from tcms.core.models import abstract
from tcms.core.models.base import UrlMixin
from tcms.testcases.fields import MultipleEmailField


class TestCaseStatus(models.Model, UrlMixin):
    name = models.CharField(verbose_name=_("Name"), max_length=255)
    description = models.TextField(verbose_name=_("Description"), null=True, blank=True)
    is_confirmed = models.BooleanField(
        verbose_name=_("Confirmed"), db_index=True, default=False
    )

    class Meta:
        verbose_name = _("Test case status")
        verbose_name_plural = _("Test case statuses")

    def __str__(self):
        return self.name


# register model for DB translations
vinaigrette.register(TestCaseStatus, ["name"])


class Category(models.Model, UrlMixin):
    name = models.CharField(verbose_name=_("Name"), max_length=255)
    product = models.ForeignKey(
        "management.Product",
        verbose_name=_("Product"),
        related_name="category",
        on_delete=models.CASCADE,
    )
    description = models.TextField(verbose_name=_("Description"), blank=True)

    class Meta:
        verbose_name = _("Category")
        ordering = ["name"]
        verbose_name_plural = _("Categories")
        unique_together = ("product", "name")

    def __str__(self):
        return self.name


class TestCase(models.Model, UrlMixin):
    history = KiwiHistoricalRecords()

    create_date = models.DateTimeField(
        verbose_name=_("Creation date"), auto_now_add=True
    )
    is_automated = models.BooleanField(verbose_name=_("Automated"), default=False)
    script = models.TextField(verbose_name=_("Script"), blank=True, null=True)
    arguments = models.TextField(verbose_name=_("Arguments"), blank=True, null=True)
    extra_link = models.URLField(
        verbose_name=_("Extra link"),
        max_length=1024,
        default=None,
        blank=True,
        null=True,
        validators=[URLValidator(schemes=["http", "https", "ftp", "ftps"])],
    )
    summary = models.CharField(verbose_name=_("Summary"), max_length=255, db_index=True)
    requirement = models.CharField(
        verbose_name=_("Requirement"), max_length=255, blank=True, null=True
    )
    notes = models.TextField(verbose_name=_("Notes"), blank=True, null=True)
    text = models.TextField(verbose_name=_("Text"), blank=True)
    setup_duration = models.DurationField(
        verbose_name=_("Setup duration"), db_index=True, null=True, blank=True
    )
    testing_duration = models.DurationField(
        verbose_name=_("Testing duration"), db_index=True, null=True, blank=True
    )

    case_status = models.ForeignKey(
        TestCaseStatus, verbose_name=_("Case status"), on_delete=models.CASCADE
    )
    category = models.ForeignKey(
        Category,
        verbose_name=_("Category"),
        related_name="category_case",
        on_delete=models.CASCADE,
    )
    priority = models.ForeignKey(
        "management.Priority",
        verbose_name=_("Priority"),
        related_name="priority_case",
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Author"),
        related_name="cases_as_author",
        on_delete=models.CASCADE,
    )
    default_tester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Default tester"),
        related_name="cases_as_default_tester",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Reviewer"),
        related_name="cases_as_reviewer",
        null=True,
        on_delete=models.CASCADE,
    )

    plan = models.ManyToManyField(
        "testplans.TestPlan",
        verbose_name=_("Test plan"),
        related_name="cases",
        through="testcases.TestCasePlan",
    )

    component = models.ManyToManyField(
        "management.Component",
        verbose_name=_("Component"),
        related_name="cases",
        through="testcases.TestCaseComponent",
    )

    tag = models.ManyToManyField(
        "management.Tag",
        verbose_name=_("Tag"),
        related_name="case",
        through="testcases.TestCaseTag",
    )

    @property
    def expected_duration(self):
        result = timedelta(0)
        result += self.setup_duration or timedelta(0)
        result += self.testing_duration or timedelta(0)
        return result

    def __str__(self):
        return self.summary

    def add_component(self, component):
        return TestCaseComponent.objects.get_or_create(case=self, component=component)

    def add_tag(self, tag):
        return TestCaseTag.objects.get_or_create(case=self, tag=tag)

    def get_text_with_version(self, case_text_version=None):
        if case_text_version:
            try:
                return self.history.get(  # pylint: disable=no-member
                    history_id=case_text_version
                ).text
            except ObjectDoesNotExist:
                return self.text

        return self.text

    def remove_component(self, component):
        # note: cannot use self.component.remove(component) on a ManyToManyField
        # which specifies an intermediary model so we use the model manager!
        self.component.through.objects.filter(
            case=self.pk, component=component.pk
        ).delete()

    def remove_tag(self, tag):
        self.tag.through.objects.filter(case=self.pk, tag=tag.pk).delete()

    def _get_absolute_url(self, request=None):
        return reverse(
            "testcases-get",
            args=[
                self.pk,
            ],
        )

    def get_absolute_url(self):
        return self._get_absolute_url()

    def _get_email_conf(self):
        try:
            # note: this is the reverse_name of a 1-to-1 field
            return self.email_settings  # pylint: disable=no-member
        except ObjectDoesNotExist:
            return TestCaseEmailSettings.objects.create(case=self)

    emailing = property(_get_email_conf)

    def clone(self, new_author, test_plans):
        values = {
            field.attname: getattr(self, field.attname)
            for field in self._meta.concrete_fields
            if not field.primary_key
        }
        sortkey = getattr(self, "sortkey", None)

        values["case_status_id"] = (
            TestCaseStatus.objects.filter(is_confirmed=False).first().pk
        )
        values["author_id"] = new_author.pk

        new_tc = self.__class__.objects.create(**values)

        # apply tags as well
        for tag in self.tag.all():
            new_tc.add_tag(tag)

        for plan in test_plans:
            plan.add_case(new_tc, sortkey)

            # clone TC category b/c we may be cloning a 'linked'
            # TC which has a different Product that doesn't have the
            # same categories yet
            try:
                tc_category = plan.product.category.get(name=self.category.name)
            except ObjectDoesNotExist:
                tc_category = plan.product.category.create(
                    name=self.category.name,
                    description=self.category.description,
                )
            new_tc.category = tc_category
            new_tc.save()

            # clone TC components b/c we may be cloning a 'linked'
            # TC which has a different Product that doesn't have the
            # same components yet
            for component in self.component.all():
                try:
                    new_component = plan.product.component.get(name=component.name)
                except ObjectDoesNotExist:
                    new_component = plan.product.component.create(
                        name=component.name,
                        initial_owner=new_author,
                        description=component.description,
                    )
                new_tc.add_component(new_component)

        from tcms.workflow.services import clone_case_workflow

        clone_case_workflow(self, new_tc)
        return new_tc

    class Meta:
        verbose_name = _("Test case")
        verbose_name_plural = _("Test cases")


class Property(abstract.Property):
    case = models.ForeignKey(
        TestCase, verbose_name=_("Test case"), on_delete=models.CASCADE
    )


class TestCasePlan(models.Model):
    plan = models.ForeignKey(
        "testplans.TestPlan", verbose_name=_("Test plan"), on_delete=models.CASCADE
    )
    case = models.ForeignKey(
        TestCase, verbose_name=_("Test case"), on_delete=models.CASCADE
    )
    sortkey = models.IntegerField(verbose_name=_("Sort order"), null=True, blank=True)

    class Meta:
        verbose_name = _("Test case plan")
        verbose_name_plural = _("Test case plans")
        unique_together = ("plan", "case")


class TestCaseComponent(models.Model):
    case = models.ForeignKey(
        TestCase, verbose_name=_("Test case"), on_delete=models.CASCADE
    )
    component = models.ForeignKey(
        "management.Component", verbose_name=_("Component"), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Test case component")
        verbose_name_plural = _("Test case components")


class TestCaseTag(models.Model):
    tag = models.ForeignKey(
        "management.Tag", verbose_name=_("Tag"), on_delete=models.CASCADE
    )
    case = models.ForeignKey(
        TestCase, verbose_name=_("Test case"), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Test case tag")
        verbose_name_plural = _("Test case tags")


class BugSystem(models.Model, UrlMixin):
    """
    This model describes a bug tracking system used in
    Kiwi TCMS. Fields below can be configured via
    the admin interface and their meaning is:

    #. **name:** a visual name for this bug tracker, e.g. `Kiwi TCMS GitHub`;
    #. **tracker_type:** a select menu to specify what kind of external
       system we interface with, e.g. Bugzilla, JIRA, others;
       The available options for this field are automatically populated
       by Kiwi TCMS;

       .. warning::

            Once this field is set it can't be reset to ``NULL``. Although
            Kiwi TCMS takes care to handle misconfigurations we advise you to
            configure your API credentials properly!

    #. **base_url:** base URL of this bug tracker.

       .. warning::

            If this field is left empty funtionality that depends on it will be disabled!

    #. **api_url, api_username, api_password:** configuration for an internal RPC object
       that communicate to the issue tracking system when necessary. Depending on the
       actual type of IT we're interfacing with some of these values may not be necessary.
       Refer to :mod:`tcms.issuetracker.types` for more information!

       .. warning::

            This is saved as plain-text in the database because it needs to be passed
            to the internal RPC object!
    """

    name = models.CharField(verbose_name=_("Name"), max_length=255, unique=True)
    tracker_type = models.CharField(  # pylint:disable=form-field-help-text-used
        max_length=128,
        verbose_name=_("Type"),
        help_text=_("This determines how Kiwi TCMS integrates with the IT system"),
        default="IssueTrackerType",
    )

    base_url = models.URLField(  # pylint:disable=form-field-help-text-used
        max_length=1024,
        null=True,
        blank=True,
        verbose_name=_("Base URL"),
        help_text=_(
            "Base URL, for example <strong>https://bugzilla.example.com</strong>!\nLeave empty to disable!\n"
        ),
        validators=[URLValidator(schemes=["http", "https"])],
    )

    api_url = models.URLField(  # pylint:disable=form-field-help-text-used
        max_length=1024,
        null=True,
        blank=True,
        verbose_name=_("API URL"),
        help_text=_(
            "This is the URL to which API requests will be sent. Leave empty to disable!"
        ),
        validators=[URLValidator(schemes=["http", "https"])],
    )

    api_username = models.CharField(
        max_length=256, null=True, blank=True, verbose_name=_("API username")
    )

    api_password = models.CharField(
        max_length=256, null=True, blank=True, verbose_name=_("API password or token")
    )

    class Meta:
        verbose_name = _("Bug tracker")
        verbose_name_plural = _("Bug trackers")

    def __str__(self):
        return self.name


class TestCaseEmailSettings(models.Model):
    case = models.OneToOneField(
        TestCase,
        verbose_name=_("Test case"),
        related_name="email_settings",
        on_delete=models.CASCADE,
    )
    notify_on_case_update = models.BooleanField(
        verbose_name=_("Notify on case update"), default=True
    )
    notify_on_case_delete = models.BooleanField(
        verbose_name=_("Notify on case delete"), default=True
    )
    auto_to_case_author = models.BooleanField(
        verbose_name=_("Auto to case author"), default=True
    )
    auto_to_case_tester = models.BooleanField(
        verbose_name=_("Auto to case tester"), default=True
    )
    auto_to_run_manager = models.BooleanField(
        verbose_name=_("Auto to run manager"), default=True
    )
    auto_to_run_tester = models.BooleanField(
        verbose_name=_("Auto to run tester"), default=True
    )
    auto_to_execution_assignee = models.BooleanField(
        verbose_name=_("Auto to execution assignee"), default=True
    )

    cc_list = models.TextField(verbose_name=_("CC list"), default="")

    def add_cc(self, email_addrs):
        """Add email addresses to CC list

        Arguments:
        - email_addrs: str or list, holding one or more email addresses
        """

        emailaddr_list = self.get_cc_list()
        if not isinstance(email_addrs, list):
            email_addrs = [email_addrs]

        # skip addresses already in the list
        for address in email_addrs:
            if address not in emailaddr_list:
                emailaddr_list.append(address)

        self.cc_list = MultipleEmailField.delimiter.join(emailaddr_list)
        self.save()

    def get_cc_list(self):
        """Return the whole CC list"""
        if not self.cc_list:
            return []
        return self.cc_list.split(MultipleEmailField.delimiter)

    def remove_cc(self, email_addrs):
        """Remove one or more email addresses from EmailSettings' CC list

        If any email_addr is unknown, remove_cc will keep quiet.

        Arguments:
        - email_addrs: str or list, holding one or more email addresses
        """
        emailaddr_list = self.get_cc_list()
        if not isinstance(email_addrs, list):
            email_addrs = [email_addrs]
        for address in email_addrs:
            if address in emailaddr_list:
                emailaddr_list.remove(address)

        self.cc_list = MultipleEmailField.delimiter.join(emailaddr_list)
        self.save()

    class Meta:
        verbose_name = _("Test case email settings")
        verbose_name_plural = _("Test case email settings")


class Template(models.Model):
    history = KiwiHistoricalRecords()

    name = models.CharField(verbose_name=_("Name"), max_length=255)
    text = models.TextField(verbose_name=_("Text"), blank=False)

    class Meta:
        verbose_name = _("Template")
        verbose_name_plural = _("Templates")

    def __str__(self):
        return self.name
