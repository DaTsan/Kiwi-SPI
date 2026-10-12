from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory
from django.utils.translation import gettext_lazy as _
from tcms.management.models import Build, Product
from tcms.testplans.models import TestPlan
from tcms.testruns.models import Environment, TestExecutionStatus, TestRun

from .models import CustomField, Milestone, SharedStepSet, TestCycle
from .services import visible, visible_runs


def style(form):
    for field in form.fields.values():
        if not isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
            field.widget.attrs.setdefault("class", "form-control")


class ScopedForm(forms.ModelForm):
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = visible(
            user, Product, "management.view_product"
        )
        if self.instance.pk:
            self.fields["product"].disabled = True
        style(self)


class MilestoneForm(ScopedForm):
    class Meta:
        model = Milestone
        fields = [
            "product",
            "name",
            "parent",
            "description",
            "references",
            "start_date",
            "due_date",
            "status",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["parent"].queryset = visible(
            user, Milestone, "workflow.view_milestone"
        ).exclude(pk=self.instance.pk)


class CycleForm(ScopedForm):
    class Meta:
        model = TestCycle
        fields = ["product", "name", "description", "milestone", "is_completed"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["milestone"].queryset = visible(
            user, Milestone, "workflow.view_milestone"
        )
        if self.instance.pk and self.instance.runs.exists():
            self.fields["milestone"].disabled = True


class SharedStepForm(ScopedForm):
    class Meta:
        model = SharedStepSet
        fields = ["product", "name"]


class CustomFieldForm(ScopedForm):
    choices = forms.CharField(
        label=_("Choices"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text=_("For Select: one option per line."),
    )

    class Meta:
        model = CustomField
        fields = [
            "product",
            "entity",
            "key",
            "label",
            "kind",
            "required",
            "choices",
            "is_active",
        ]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if self.instance.pk:
            self.initial["choices"] = "\n".join(self.instance.choices)
            for key in ("entity", "key", "kind"):
                self.fields[key].disabled = True

    def clean_choices(self):
        return [
            line.strip()
            for line in self.cleaned_data["choices"].splitlines()
            if line.strip()
        ]


class StepForm(forms.Form):
    action = forms.CharField(
        label=_("Action"),
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    expected = forms.CharField(
        label=_("Expected result"),
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    reference = forms.CharField(label=_("Reference"), required=False, max_length=255)
    shared = forms.ModelChoiceField(
        label=_("Shared step set"),
        queryset=SharedStepSet.objects.none(),
        required=False,
    )

    def __init__(self, *args, product_id, user=None, shared_allowed=True, **kwargs):
        super().__init__(*args, **kwargs)
        if shared_allowed:
            queryset = (
                visible(user, SharedStepSet, "workflow.view_sharedstepset")
                if user
                else SharedStepSet.objects.all()
            )
            self.fields["shared"].queryset = queryset.filter(product_id=product_id)
        else:
            self.fields.pop("shared")
        style(self)

    def clean(self):
        values = super().clean()
        if values.get("DELETE"):
            return values
        if values.get("shared"):
            if (
                values.get("action")
                or values.get("expected")
                or values.get("reference")
            ):
                raise ValidationError(
                    _("Use either an inline step or a shared set, not both.")
                )
        elif not values.get("action"):
            raise ValidationError(_("Enter an action or choose a shared step set."))
        return values


class OrderedSteps(BaseFormSet):
    ordering_widget = forms.HiddenInput

    def as_steps(self):
        steps = []
        for form in self.ordered_forms:
            if not form.cleaned_data:
                continue
            values = form.cleaned_data
            if values.get("shared"):
                steps.append({"shared_id": values["shared"].pk})
            else:
                steps.append(
                    {
                        key: values.get(key, "")
                        for key in ("action", "expected", "reference")
                    }
                )
        return steps


StepFormSet = formset_factory(
    StepForm,
    formset=OrderedSteps,
    extra=0,
    can_delete=True,
    can_order=True,
    max_num=200,
    validate_max=True,
)


def step_initial(steps):
    return [
        {**step, "shared": step.get("shared_id"), "ORDER": index}
        for index, step in enumerate(steps)
    ]


class CustomValuesForm(forms.Form):
    def __init__(self, *args, product_id, entity, values=None, **kwargs):
        values = values or {}
        super().__init__(*args, **kwargs)
        self.definitions = list(
            CustomField.objects.filter(
                product_id=product_id, entity=entity, is_active=True
            )
        )
        for definition in self.definitions:
            params = {
                "label": definition.label,
                "required": definition.required,
                "initial": values.get(definition.key),
            }
            if definition.kind == "integer":
                field = forms.IntegerField(
                    min_value=-(2**63), max_value=2**63 - 1, **params
                )
            elif definition.kind == "checkbox":
                params["required"] = False  # False is a valid required boolean value.
                field = forms.BooleanField(**params)
            elif definition.kind == "select":
                field = forms.ChoiceField(
                    choices=[("", "---------")]
                    + [(item, item) for item in definition.choices],
                    **params,
                )
            elif definition.kind == "date":
                field = forms.DateField(
                    widget=forms.DateInput(attrs={"type": "date"}), **params
                )
            elif definition.kind == "url":
                field = forms.URLField(max_length=2000, **params)
            else:
                field = forms.CharField(
                    max_length=10000, widget=forms.Textarea(attrs={"rows": 2}), **params
                )
            self.fields[f"custom_{definition.key}"] = field
        style(self)

    def values(self, previous=None):
        result = dict(previous or {})
        for definition in self.definitions:
            value = self.cleaned_data[f"custom_{definition.key}"]
            if definition.kind == "date" and value:
                value = value.isoformat()
            result[definition.key] = value
        return result


class ResultForm(forms.Form):
    status = forms.ModelChoiceField(
        label=_("Status"),
        queryset=TestExecutionStatus.objects.order_by("-weight", "name"),
    )
    comment = forms.CharField(
        label=_("Comment"),
        required=False,
        max_length=50000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    elapsed_seconds = forms.IntegerField(
        required=False, min_value=0, max_value=604800, label=_("Elapsed time (seconds)")
    )
    defects = forms.CharField(
        required=False, max_length=2000, label=_("Defect references (IDs or URLs)")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style(self)


class StepResultForm(forms.Form):
    status = forms.ModelChoiceField(
        label=_("Status"),
        queryset=TestExecutionStatus.objects.order_by("-weight", "name"),
    )
    actual = forms.CharField(
        label=_("Actual result"),
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style(self)


StepResultFormSet = formset_factory(
    StepResultForm, extra=0, max_num=500, validate_max=True
)


class ConfigurationRunForm(forms.Form):
    plan = forms.ModelChoiceField(
        label=_("Test plan"), queryset=TestPlan.objects.none()
    )
    build = forms.ModelChoiceField(label=_("Build"), queryset=Build.objects.none())
    environments = forms.ModelMultipleChoiceField(
        label=_("Environments"),
        queryset=Environment.objects.none(),
        required=False,
        help_text=_(
            "Each selected environment creates a separate run. Leave empty for one default run."
        ),
    )

    def __init__(self, *args, user, cycle, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = visible(
            user, TestPlan, "testplans.view_testplan"
        ).filter(product_id=cycle.product_id)
        self.fields["build"].queryset = visible(
            user, Build, "management.view_build"
        ).filter(version__product_id=cycle.product_id, is_active=True)
        self.fields["environments"].queryset = visible(
            user, Environment, "testruns.view_environment"
        )
        style(self)


class LinkRunForm(forms.Form):
    run = forms.ModelChoiceField(label=_("Test run"), queryset=TestRun.objects.none())

    def __init__(self, *args, user, cycle, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["run"].queryset = (
            visible_runs(user)
            .filter(plan__product_id=cycle.product_id)
            .filter(cycle_link__isnull=True)
        )
        style(self)


class RunPlanningForm(forms.Form):
    milestone = forms.ModelChoiceField(
        label=_("Milestone"), queryset=Milestone.objects.none(), required=False
    )
    cycle = forms.ModelChoiceField(
        label=_("Test cycle"), queryset=TestCycle.objects.none(), required=False
    )

    def __init__(self, *args, user, run, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["milestone"].queryset = visible(
            user, Milestone, "workflow.view_milestone"
        ).filter(product_id=run.plan.product_id)
        self.fields["cycle"].queryset = visible(
            user, TestCycle, "workflow.view_testcycle"
        ).filter(product_id=run.plan.product_id)
        style(self)
