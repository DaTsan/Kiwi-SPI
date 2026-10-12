from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from tcms.core.history import KiwiHistoricalRecords

from .validators import validate_choices, validate_shared_steps, validate_steps


class Milestone(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", _("Upcoming")
        OPEN = "open", _("Open")
        COMPLETED = "completed", _("Completed")

    product = models.ForeignKey(
        "management.Product", verbose_name=_("Product"), on_delete=models.CASCADE
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("Parent milestone"),
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    name = models.CharField(verbose_name=_("Name"), max_length=255)
    description = models.TextField(verbose_name=_("Description"), blank=True)
    references = models.CharField(
        verbose_name=_("References"), max_length=1000, blank=True
    )
    start_date = models.DateField(verbose_name=_("Start date"), blank=True, null=True)
    due_date = models.DateField(verbose_name=_("Due date"), blank=True, null=True)
    status = models.CharField(
        verbose_name=_("Status"),
        max_length=12,
        choices=Status.choices,
        default=Status.OPEN,
    )
    history = KiwiHistoricalRecords()

    class Meta:
        verbose_name = _("Milestone")
        verbose_name_plural = _("Milestones")
        ordering = ["due_date", "name", "pk"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("workflow:milestone", args=[self.pk])

    def clean(self):
        super().clean()
        if (
            self.pk
            and type(self)
            .objects.filter(pk=self.pk)
            .exclude(product_id=self.product_id)
            .exists()
        ):
            raise ValidationError({"product": _("Product cannot be changed.")})
        if self.start_date and self.due_date and self.start_date > self.due_date:
            raise ValidationError(
                {"due_date": _("End date must not precede start date.")}
            )
        visited = {self.pk} if self.pk else set()
        parent = self.parent
        while parent:
            if parent.pk in visited:
                raise ValidationError(
                    {"parent": _("Milestone hierarchy cannot contain a cycle.")}
                )
            if parent.product_id != self.product_id:
                raise ValidationError(
                    {"parent": _("Parent must belong to the same product.")}
                )
            visited.add(parent.pk)
            parent = parent.parent


class TestCycle(models.Model):
    product = models.ForeignKey(
        "management.Product", verbose_name=_("Product"), on_delete=models.CASCADE
    )
    milestone = models.ForeignKey(
        Milestone,
        verbose_name=_("Milestone"),
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    name = models.CharField(verbose_name=_("Name"), max_length=255)
    description = models.TextField(verbose_name=_("Description"), blank=True)
    is_completed = models.BooleanField(verbose_name=_("Completed"), default=False)
    runs = models.ManyToManyField(
        "testruns.TestRun",
        verbose_name=_("Test runs"),
        through="CycleRun",
        related_name="test_cycles",
    )
    history = KiwiHistoricalRecords()

    class Meta:
        verbose_name = _("Test cycle")
        verbose_name_plural = _("Test cycles")
        ordering = ["-pk"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("workflow:cycle", args=[self.pk])

    def clean(self):
        super().clean()
        if self.milestone_id and self.milestone.product_id != self.product_id:
            raise ValidationError(
                {"milestone": _("Milestone must belong to the same product.")}
            )
        if self.pk and self.runs.exists():
            previous = type(self).objects.get(pk=self.pk)
            if (
                previous.product_id != self.product_id
                or previous.milestone_id != self.milestone_id
            ):
                raise ValidationError(
                    _("Product and milestone cannot be changed after adding runs.")
                )


class CycleRun(models.Model):
    cycle = models.ForeignKey(
        TestCycle, verbose_name=_("Test cycle"), on_delete=models.CASCADE
    )
    run = models.OneToOneField(
        "testruns.TestRun",
        verbose_name=_("Test run"),
        on_delete=models.CASCADE,
        related_name="cycle_link",
    )

    def clean(self):
        super().clean()
        if (
            self.cycle_id
            and self.run_id
            and self.cycle.product_id != self.run.plan.product_id
        ):
            raise ValidationError(_("Run and cycle must belong to the same product."))

    class Meta:
        verbose_name = _("Cycle run")
        verbose_name_plural = _("Cycle runs")


class RunMilestone(models.Model):
    run = models.OneToOneField(
        "testruns.TestRun",
        verbose_name=_("Test run"),
        on_delete=models.CASCADE,
        related_name="milestone_link",
    )
    milestone = models.ForeignKey(
        Milestone,
        verbose_name=_("Milestone"),
        on_delete=models.PROTECT,
        related_name="run_links",
    )

    def clean(self):
        super().clean()
        if (
            self.run_id
            and self.milestone_id
            and self.run.plan.product_id != self.milestone.product_id
        ):
            raise ValidationError(
                _("Run and milestone must belong to the same product.")
            )

    class Meta:
        verbose_name = _("Run milestone")
        verbose_name_plural = _("Run milestones")


class SharedStepSet(models.Model):
    product = models.ForeignKey(
        "management.Product", verbose_name=_("Product"), on_delete=models.CASCADE
    )
    name = models.CharField(verbose_name=_("Name"), max_length=255)
    steps = models.JSONField(
        verbose_name=_("Steps"),
        default=list,
        blank=True,
        validators=[validate_shared_steps],
    )
    history = KiwiHistoricalRecords()

    class Meta:
        verbose_name = _("Shared step set")
        verbose_name_plural = _("Shared step sets")
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if (
            self.pk
            and type(self)
            .objects.filter(pk=self.pk)
            .exclude(product_id=self.product_id)
            .exists()
        ):
            raise ValidationError({"product": _("Product cannot be changed.")})


class CustomField(models.Model):
    class Entity(models.TextChoices):
        CASE = "case", _("Test case")
        RESULT = "result", _("Test result")

    class Kind(models.TextChoices):
        TEXT = "text", _("Text")
        INTEGER = "integer", _("Integer")
        CHECKBOX = "checkbox", _("Checkbox")
        SELECT = "select", pgettext_lazy("custom field type", "Select")
        DATE = "date", _("Date")
        URL = "url", _("URL")

    product = models.ForeignKey(
        "management.Product", verbose_name=_("Product"), on_delete=models.CASCADE
    )
    entity = models.CharField(
        verbose_name=_("Entity"), max_length=6, choices=Entity.choices
    )
    key = models.SlugField(verbose_name=_("Key"), max_length=64)
    label = models.CharField(verbose_name=_("Label"), max_length=255)
    kind = models.CharField(verbose_name=_("Type"), max_length=8, choices=Kind.choices)
    required = models.BooleanField(verbose_name=_("Required"), default=False)
    choices = models.JSONField(
        verbose_name=_("Choices"),
        default=list,
        blank=True,
        validators=[validate_choices],
    )
    is_active = models.BooleanField(verbose_name=_("Active"), default=True)
    history = KiwiHistoricalRecords()

    class Meta:
        verbose_name = _("Custom field")
        verbose_name_plural = _("Custom fields")
        ordering = ["label", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "entity", "key"], name="workflow_field_key"
            )
        ]

    def __str__(self):
        return self.label

    def clean(self):
        super().clean()
        if self.kind == self.Kind.SELECT and not self.choices:
            raise ValidationError(
                {"choices": _("Select fields need at least one choice.")}
            )
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            for field in ("product_id", "entity", "key", "kind"):
                if getattr(previous, field) != getattr(self, field):
                    raise ValidationError(
                        _(
                            "Product, entity, key and type cannot be changed; create another field."
                        )
                    )


class CaseWorkflow(models.Model):
    case = models.OneToOneField(
        "testcases.TestCase",
        verbose_name=_("Test case"),
        on_delete=models.CASCADE,
        related_name="workflow",
    )
    steps = models.JSONField(
        verbose_name=_("Steps"), default=list, blank=True, validators=[validate_steps]
    )
    custom_values = models.JSONField(
        verbose_name=_("Custom values"), default=dict, blank=True
    )
    history = KiwiHistoricalRecords()

    def clean(self):
        super().clean()
        from .services import resolve_steps, validate_custom_values

        if self.case_id:
            resolve_steps(self.steps, self.case.category.product_id)
            validate_custom_values(
                self.case.category.product_id, "case", self.custom_values
            )

    class Meta:
        verbose_name = _("Case workflow")
        verbose_name_plural = _("Case workflows")


class ExecutionSnapshot(models.Model):
    execution = models.OneToOneField(
        "testruns.TestExecution",
        verbose_name=_("Test execution"),
        on_delete=models.CASCADE,
        related_name="workflow_snapshot",
    )
    case_summary = models.CharField(verbose_name=_("Case summary"), max_length=255)
    requirement = models.CharField(
        verbose_name=_("Requirement"), max_length=255, blank=True
    )
    steps = models.JSONField(verbose_name=_("Steps"), default=list)
    case_fields = models.JSONField(verbose_name=_("Case fields"), default=dict)
    captured_at = models.DateTimeField(verbose_name=_("Captured at"), auto_now_add=True)
    legacy = models.BooleanField(verbose_name=_("Legacy snapshot"), default=False)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(_("Execution snapshots cannot be changed."))
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Execution snapshot")
        verbose_name_plural = _("Execution snapshots")


class ExecutionResult(models.Model):
    execution = models.ForeignKey(
        "testruns.TestExecution",
        verbose_name=_("Test execution"),
        on_delete=models.CASCADE,
        related_name="results",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Author"),
        null=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(verbose_name=_("Created at"), auto_now_add=True)
    status = models.ForeignKey(
        "testruns.TestExecutionStatus",
        verbose_name=_("Status"),
        on_delete=models.PROTECT,
    )
    status_label = models.CharField(verbose_name=_("Status label"), max_length=60)
    status_weight = models.IntegerField(
        verbose_name=_("Status weight"),
    )
    comment = models.TextField(verbose_name=_("Comment"), blank=True)
    elapsed_seconds = models.PositiveIntegerField(
        verbose_name=_("Elapsed time (seconds)"), blank=True, null=True
    )
    defects = models.CharField(verbose_name=_("Defects"), max_length=2000, blank=True)
    step_results = models.JSONField(verbose_name=_("Step results"), default=list)
    custom_values = models.JSONField(verbose_name=_("Custom values"), default=dict)

    class Meta:
        verbose_name = _("Execution result")
        verbose_name_plural = _("Execution results")
        ordering = ["-created_at", "-pk"]
        default_permissions = ("add", "view")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                _("Results are append-only; add another result instead.")
            )
        return super().save(*args, **kwargs)
