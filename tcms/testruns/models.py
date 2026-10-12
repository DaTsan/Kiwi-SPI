# -*- coding: utf-8 -*-
import itertools
from collections import OrderedDict, namedtuple

import vinaigrette
from allpairspy import AllPairs
from colorfield.fields import ColorField
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from tcms.core.contrib.linkreference.models import LinkReference
from tcms.core.history import KiwiHistoricalRecords
from tcms.core.models import abstract
from tcms.core.models.base import UrlMixin

TestExecutionStatusSubtotal = namedtuple(
    "TestExecutionStatusSubtotal",
    [
        "CompletedPercentage",
        "FailurePercentage",
        "SuccessPercentage",
    ],
)


class TestRun(models.Model, UrlMixin):
    history = KiwiHistoricalRecords()

    start_date = models.DateTimeField(
        verbose_name=_("Start date"), db_index=True, null=True, blank=True
    )
    stop_date = models.DateTimeField(
        verbose_name=_("Stop date"), null=True, blank=True, db_index=True
    )
    planned_start = models.DateTimeField(
        verbose_name=_("Planned start"), db_index=True, null=True, blank=True
    )
    planned_stop = models.DateTimeField(
        verbose_name=_("Planned stop"), db_index=True, null=True, blank=True
    )

    summary = models.TextField(
        verbose_name=_("Summary"),
    )
    notes = models.TextField(verbose_name=_("Notes"), blank=True)

    plan = models.ForeignKey(
        "testplans.TestPlan",
        verbose_name=_("Test plan"),
        related_name="run",
        on_delete=models.CASCADE,
    )
    build = models.ForeignKey(
        "management.Build",
        verbose_name=_("Build"),
        related_name="build_run",
        on_delete=models.CASCADE,
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Manager"),
        related_name="manager",
        on_delete=models.CASCADE,
    )
    default_tester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Default tester"),
        null=True,
        blank=True,
        related_name="default_tester",
        on_delete=models.CASCADE,
    )

    tag = models.ManyToManyField(
        "management.Tag",
        verbose_name=_("Tag"),
        through="testruns.TestRunTag",
        related_name="run",
    )

    cc = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("Cc"), through="testruns.TestRunCC"
    )

    def __str__(self):
        return self.summary

    def _get_absolute_url(self):
        return reverse(
            "testruns-get",
            args=[
                self.pk,
            ],
        )

    def get_absolute_url(self):
        return self._get_absolute_url()

    def get_notify_addrs(self):
        """
        Get the all related mails from the run
        """
        send_to = []
        if self.manager.is_active:
            send_to.append(self.manager.email)
        send_to.extend(self.cc.filter(is_active=True).values_list("email", flat=True))
        if self.default_tester_id and self.default_tester.is_active:
            send_to.append(self.default_tester.email)

        for execution in self.executions.select_related("assignee").filter(
            assignee__is_active=True
        ):
            if execution.assignee_id:
                send_to.append(execution.assignee.email)

        send_to = set(send_to)
        # don't email author of last change
        send_to.discard(
            getattr(
                self.history.latest().history_user,  # pylint: disable=no-member
                "email",
                "",
            )
        )
        return list(send_to)

    def _create_single_execution(self, case, assignee, build, sortkey):
        return self.executions.create(
            case=case,
            assignee=assignee,
            tested_by=None,
            # usually IDLE but users can customize statuses
            status=TestExecutionStatus.objects.filter(weight=0).first(),
            case_text_version=case.history.latest().history_id,
            build=build or self.build,
            sortkey=sortkey,
            stop_date=None,
            start_date=None,
        )

    def create_execution(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        case,
        assignee=None,
        build=None,
        sortkey=0,
        matrix_type="full",
    ):
        # pylint: disable=import-outside-toplevel
        from tcms.testcases.models import Property as TestCaseProperty

        assignee = (
            assignee
            or (case.default_tester_id and case.default_tester)
            or (self.default_tester_id and self.default_tester)
        )

        executions = []
        properties = self.property_set.union(TestCaseProperty.objects.filter(case=case))

        if properties.count():
            for prop_tuple in self.property_matrix(properties, matrix_type):
                execution = self._create_single_execution(
                    case, assignee, build, sortkey
                )
                executions.append(execution)

                for prop in prop_tuple:
                    TestExecutionProperty.objects.create(
                        execution=execution, name=prop.name, value=prop.value
                    )
        else:
            executions.append(
                self._create_single_execution(case, assignee, build, sortkey)
            )

        return executions

    @staticmethod
    def property_matrix(properties, _type="full"):
        """
        Return a sequence of tuples representing the property matrix!
        """
        property_groups = OrderedDict()
        for prop in properties.order_by("name", "value"):
            if prop.name in property_groups:
                # do not repeat non-distinct values
                if prop not in property_groups[prop.name]:
                    property_groups[prop.name].append(prop)
            else:
                property_groups[prop.name] = [prop]

        if _type == "full":
            return itertools.product(*property_groups.values())

        if _type == "pairwise":
            # AllPairs returns named tuples which require valid identifiers.
            # Rename all keys b/c we don't use them for storing data in DB anyway
            for _i, key in enumerate(property_groups.copy()):
                property_groups[f"key_{_i}"] = property_groups.pop(key)

            # Note: in Python 3.10 there is itertools.pairwise() function
            return AllPairs(property_groups)

        raise RuntimeError(f"Unknown matrix type '{_type}'")

    def add_tag(self, tag):
        return TestRunTag.objects.get_or_create(run=self, tag=tag)

    def add_cc(self, user):
        return TestRunCC.objects.get_or_create(
            run=self,
            user=user,
        )

    def remove_tag(self, tag):
        TestRunTag.objects.filter(run=self, tag=tag).delete()

    def remove_cc(self, user):
        TestRunCC.objects.filter(run=self, user=user).delete()

    @override("en")
    def stats_executions_status(self):
        """
        Get statistics based on executions' status

        :return: the statistics including the number of each status mapping,
                 total number of executions, complete percent, and failure percent.
        :rtype: namedtuple
        """
        total_count = self.executions.count()
        if total_count:
            complete_count = self.executions.exclude(status__weight=0).count()
            complete_percent = complete_count * 100.0 / total_count

            failing_count = self.executions.filter(status__weight__lt=0).count()
            failing_percent = failing_count * 100.0 / total_count
        else:
            complete_percent = 0.0
            failing_percent = 0.0

        return TestExecutionStatusSubtotal(
            complete_percent,
            failing_percent,
            complete_percent - failing_percent,
        )

    class Meta:
        verbose_name = _("Test run")
        verbose_name_plural = _("Test runs")


class TestExecutionStatus(models.Model, UrlMixin):
    class Meta:
        verbose_name = _("Test execution status")
        # used in the admin view
        verbose_name_plural = _("Test execution statuses")

    name = models.CharField(
        verbose_name=_("Name"), max_length=60, blank=True, unique=True
    )
    weight = models.IntegerField(verbose_name=_("Weight"), default=0)
    icon = models.CharField(verbose_name=_("Icon"), max_length=64)
    color = ColorField(verbose_name=_("Color"))

    def __str__(self):
        return self.name


# register model for DB translations
vinaigrette.register(TestExecutionStatus, ["name"])


class TestExecution(models.Model, UrlMixin):
    history = KiwiHistoricalRecords()

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Assignee"),
        blank=True,
        null=True,
        related_name="execution_assignee",
        on_delete=models.CASCADE,
    )
    tested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Tested by"),
        blank=True,
        null=True,
        related_name="execution_tester",
        on_delete=models.CASCADE,
    )
    case_text_version = models.IntegerField(
        verbose_name=_("Case text version"),
    )
    start_date = models.DateTimeField(
        verbose_name=_("Start date"), null=True, blank=True, db_index=True
    )
    stop_date = models.DateTimeField(
        verbose_name=_("Stop date"), null=True, blank=True, db_index=True
    )
    sortkey = models.IntegerField(verbose_name=_("Sort order"), null=True, blank=True)

    run = models.ForeignKey(
        TestRun,
        verbose_name=_("Test run"),
        related_name="executions",
        on_delete=models.CASCADE,
    )
    case = models.ForeignKey(
        "testcases.TestCase",
        verbose_name=_("Test case"),
        related_name="executions",
        on_delete=models.CASCADE,
    )
    status = models.ForeignKey(
        TestExecutionStatus, verbose_name=_("Status"), on_delete=models.CASCADE
    )
    build = models.ForeignKey(
        "management.Build", verbose_name=_("Build"), on_delete=models.CASCADE
    )

    tag = models.ManyToManyField(
        "management.Tag",
        verbose_name=_("Tag"),
        through="testruns.TestExecutionTag",
        related_name="execution",
    )

    def __str__(self):
        return f"{self.pk}: {self.case_id}"

    def links(self):
        return LinkReference.objects.filter(execution=self.pk)

    def get_bugs(self):
        return self.links().filter(is_defect=True)

    def _get_absolute_url(self):
        # NOTE: this returns the URL to the TestRun containing this TestExecution!
        return reverse("testruns-get", args=[self.run_id])

    @property
    def actual_duration(self):
        if self.stop_date is None or self.start_date is None:
            return None
        return self.stop_date - self.start_date

    def properties(self):
        return TestExecutionProperty.objects.filter(execution=self.pk)

    class Meta:
        verbose_name = _("Test execution")
        verbose_name_plural = _("Test executions")


class TestExecutionProperty(abstract.Property):
    execution = models.ForeignKey(
        TestExecution, verbose_name=_("Test execution"), on_delete=models.CASCADE
    )


class TestRunTag(models.Model):
    tag = models.ForeignKey(
        "management.Tag", verbose_name=_("Tag"), on_delete=models.CASCADE
    )
    run = models.ForeignKey(
        TestRun,
        verbose_name=_("Test run"),
        related_name="tags",
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("Test run tag")
        verbose_name_plural = _("Test run tags")


class TestExecutionTag(models.Model):
    tag = models.ForeignKey(
        "management.Tag", verbose_name=_("Tag"), on_delete=models.CASCADE
    )
    execution = models.ForeignKey(
        TestExecution,
        verbose_name=_("Test execution"),
        related_name="tags",
        on_delete=models.CASCADE,
    )


class TestRunCC(models.Model):
    run = models.ForeignKey(
        TestRun,
        verbose_name=_("Test run"),
        related_name="cc_list",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("User"), on_delete=models.CASCADE
    )

    class Meta:
        unique_together = ("run", "user")


class Environment(models.Model):
    name = models.CharField(verbose_name=_("Name"), unique=True, max_length=255)
    description = models.TextField(verbose_name=_("Description"), blank=True)

    def _get_absolute_url(self):
        return reverse(
            "testruns-environment",
            args=[
                self.pk,
            ],
        )

    def get_absolute_url(self):
        return self._get_absolute_url()

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = _("Environment")
        verbose_name_plural = _("Environments")


class EnvironmentProperty(abstract.Property):
    environment = models.ForeignKey(
        Environment, verbose_name=_("Environment"), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Environment property")
        verbose_name_plural = _("Environment properties")


class Property(abstract.Property):
    run = models.ForeignKey(
        TestRun, verbose_name=_("Test run"), on_delete=models.CASCADE
    )
