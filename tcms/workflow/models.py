from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from tcms.core.history import KiwiHistoricalRecords

from .validators import validate_choices, validate_shared_steps, validate_steps


class Milestone(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        OPEN = "open", "Open"
        COMPLETED = "completed", "Completed"

    product = models.ForeignKey("management.Product", on_delete=models.CASCADE)
    parent = models.ForeignKey("self", blank=True, null=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    references = models.CharField(max_length=1000, blank=True)
    start_date = models.DateField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.OPEN
    )
    history = KiwiHistoricalRecords()

    class Meta:
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
            raise ValidationError({"product": "Product cannot be changed."})
        if self.start_date and self.due_date and self.start_date > self.due_date:
            raise ValidationError({"due_date": "End date must not precede start date."})
        visited = {self.pk} if self.pk else set()
        parent = self.parent
        while parent:
            if parent.pk in visited:
                raise ValidationError(
                    {"parent": "Milestone hierarchy cannot contain a cycle."}
                )
            if parent.product_id != self.product_id:
                raise ValidationError(
                    {"parent": "Parent must belong to the same product."}
                )
            visited.add(parent.pk)
            parent = parent.parent


class TestCycle(models.Model):
    product = models.ForeignKey("management.Product", on_delete=models.CASCADE)
    milestone = models.ForeignKey(
        Milestone, blank=True, null=True, on_delete=models.PROTECT
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    runs = models.ManyToManyField(
        "testruns.TestRun", through="CycleRun", related_name="test_cycles"
    )
    history = KiwiHistoricalRecords()

    class Meta:
        ordering = ["-pk"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("workflow:cycle", args=[self.pk])

    def clean(self):
        super().clean()
        if self.milestone_id and self.milestone.product_id != self.product_id:
            raise ValidationError(
                {"milestone": "Milestone must belong to the same product."}
            )
        if self.pk and self.runs.exists():
            previous = type(self).objects.get(pk=self.pk)
            if (
                previous.product_id != self.product_id
                or previous.milestone_id != self.milestone_id
            ):
                raise ValidationError(
                    "Product and milestone cannot be changed after adding runs."
                )


class CycleRun(models.Model):
    cycle = models.ForeignKey(TestCycle, on_delete=models.CASCADE)
    run = models.OneToOneField(
        "testruns.TestRun", on_delete=models.CASCADE, related_name="cycle_link"
    )

    def clean(self):
        super().clean()
        if (
            self.cycle_id
            and self.run_id
            and self.cycle.product_id != self.run.plan.product_id
        ):
            raise ValidationError("Run and cycle must belong to the same product.")


class RunMilestone(models.Model):
    run = models.OneToOneField(
        "testruns.TestRun", on_delete=models.CASCADE, related_name="milestone_link"
    )
    milestone = models.ForeignKey(
        Milestone, on_delete=models.PROTECT, related_name="run_links"
    )

    def clean(self):
        super().clean()
        if (
            self.run_id
            and self.milestone_id
            and self.run.plan.product_id != self.milestone.product_id
        ):
            raise ValidationError("Run and milestone must belong to the same product.")


class SharedStepSet(models.Model):
    product = models.ForeignKey("management.Product", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    steps = models.JSONField(
        default=list, blank=True, validators=[validate_shared_steps]
    )
    history = KiwiHistoricalRecords()

    class Meta:
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
            raise ValidationError({"product": "Product cannot be changed."})


class CustomField(models.Model):
    class Entity(models.TextChoices):
        CASE = "case", "Test case"
        RESULT = "result", "Test result"

    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        INTEGER = "integer", "Integer"
        CHECKBOX = "checkbox", "Checkbox"
        SELECT = "select", "Select"
        DATE = "date", "Date"
        URL = "url", "URL"

    product = models.ForeignKey("management.Product", on_delete=models.CASCADE)
    entity = models.CharField(max_length=6, choices=Entity.choices)
    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=255)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    required = models.BooleanField(default=False)
    choices = models.JSONField(default=list, blank=True, validators=[validate_choices])
    is_active = models.BooleanField(default=True)
    history = KiwiHistoricalRecords()

    class Meta:
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
                {"choices": "Select fields need at least one choice."}
            )
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            for field in ("product_id", "entity", "key", "kind"):
                if getattr(previous, field) != getattr(self, field):
                    raise ValidationError(
                        "Product, entity, key and type cannot be changed; create another field."
                    )


class CaseWorkflow(models.Model):
    case = models.OneToOneField(
        "testcases.TestCase", on_delete=models.CASCADE, related_name="workflow"
    )
    steps = models.JSONField(default=list, blank=True, validators=[validate_steps])
    custom_values = models.JSONField(default=dict, blank=True)
    history = KiwiHistoricalRecords()

    def clean(self):
        super().clean()
        from .services import resolve_steps, validate_custom_values

        if self.case_id:
            resolve_steps(self.steps, self.case.category.product_id)
            validate_custom_values(
                self.case.category.product_id, "case", self.custom_values
            )


class ExecutionSnapshot(models.Model):
    execution = models.OneToOneField(
        "testruns.TestExecution",
        on_delete=models.CASCADE,
        related_name="workflow_snapshot",
    )
    case_summary = models.CharField(max_length=255)
    requirement = models.CharField(max_length=255, blank=True)
    steps = models.JSONField(default=list)
    case_fields = models.JSONField(default=dict)
    captured_at = models.DateTimeField(auto_now_add=True)
    legacy = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Execution snapshots cannot be changed.")
        return super().save(*args, **kwargs)


class ExecutionResult(models.Model):
    execution = models.ForeignKey(
        "testruns.TestExecution", on_delete=models.CASCADE, related_name="results"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.ForeignKey("testruns.TestExecutionStatus", on_delete=models.PROTECT)
    status_label = models.CharField(max_length=60)
    status_weight = models.IntegerField()
    comment = models.TextField(blank=True)
    elapsed_seconds = models.PositiveIntegerField(blank=True, null=True)
    defects = models.CharField(max_length=2000, blank=True)
    step_results = models.JSONField(default=list)
    custom_values = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("add", "view")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "Results are append-only; add another result instead."
            )
        return super().save(*args, **kwargs)
