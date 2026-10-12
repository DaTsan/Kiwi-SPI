from copy import deepcopy
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from guardian.shortcuts import get_objects_for_user

from tcms.testplans.organization import confirmed_tree_cases
from tcms.testruns.models import (
    EnvironmentProperty,
    TestExecution,
    TestExecutionStatus,
    TestRun,
)

from .models import (
    CaseWorkflow,
    CustomField,
    CycleRun,
    ExecutionResult,
    ExecutionSnapshot,
    RunMilestone,
    SharedStepSet,
    TestCycle,
)
from .validators import validate_steps


def allowed(user, permission, obj=None):
    return user.is_authenticated and (
        user.has_perm(permission)
        or (obj is not None and user.has_perm(permission, obj))
    )


def require(user, permission, obj=None):
    if not allowed(user, permission, obj):
        raise PermissionDenied


def visible(user, model, permission):
    return get_objects_for_user(user, permission, klass=model, accept_global_perms=True)


def visible_runs(user):
    return visible(user, TestRun, "testruns.view_testrun").select_related(
        "plan__product", "build"
    )


def visible_executions(user):
    return visible(user, TestExecution, "testruns.view_testexecution").filter(
        run_id__in=visible_runs(user).values("pk")
    )


def resolve_steps(steps, product_id):
    validate_steps(steps)
    ids = {step["shared_id"] for step in steps if "shared_id" in step}
    shared = {
        item.pk: item
        for item in SharedStepSet.objects.filter(pk__in=ids, product_id=product_id)
    }
    if ids - shared.keys():
        raise ValidationError(
            _("A shared step set is missing or belongs to another product.")
        )
    resolved = []
    for step in steps:
        if "shared_id" in step:
            block = shared[step["shared_id"]]
            for item in block.steps:
                resolved.append({**deepcopy(item), "shared_name": block.name})
        else:
            resolved.append(deepcopy(step))
    if len(resolved) > 500:
        raise ValidationError(
            _("Expanded scenario cannot contain more than 500 steps.")
        )
    return resolved


def validate_custom_values(product_id, entity, values):
    if not isinstance(values, dict):
        raise ValidationError(_("Custom values must be an object."))
    definitions = {
        field.key: field
        for field in CustomField.objects.filter(product_id=product_id, entity=entity)
    }
    if values.keys() - definitions.keys():
        raise ValidationError(_("Unknown custom field or field from another product."))
    errors = []
    for key, field in definitions.items():
        value = values.get(key)
        missing = value is None or value == ""
        if missing:
            if field.is_active and field.required:
                errors.append(
                    _("%(field)s: value is required.") % {"field": field.label}
                )
            continue
        valid = True
        if field.kind == "integer":
            valid = type(value) is int and -(2**63) <= value < 2**63
        elif field.kind == "checkbox":
            valid = type(value) is bool
        elif field.kind == "select":
            valid = isinstance(value, str) and value in field.choices
        elif field.kind == "date":
            try:
                valid = (
                    isinstance(value, str)
                    and date.fromisoformat(value).isoformat() == value
                )
            except (ValueError, TypeError):
                valid = False
        elif field.kind == "url":
            try:
                valid = isinstance(value, str) and len(value) <= 2000
                if valid:
                    URLValidator(schemes=["http", "https"])(value)
            except ValidationError:
                valid = False
        else:
            valid = isinstance(value, str) and len(value) <= 10000
        if not valid:
            errors.append(
                _("%(field)s: invalid %(kind)s value.")
                % {"field": field.label, "kind": field.get_kind_display()}
            )
    if errors:
        raise ValidationError(errors)
    return values


def snapshot_execution(execution, legacy=False):
    existing = ExecutionSnapshot.objects.filter(execution=execution).first()
    if existing:
        return existing
    workflow = CaseWorkflow.objects.filter(case_id=execution.case_id).first()
    product_id = execution.case.category.product_id
    values = workflow.custom_values if workflow else {}
    labels = {
        field.key: field.label
        for field in CustomField.objects.filter(product_id=product_id, entity="case")
    }
    snapshot, _created = ExecutionSnapshot.objects.get_or_create(
        execution=execution,
        defaults={
            "case_summary": execution.case.summary,
            "requirement": execution.case.requirement or "",
            "steps": resolve_steps(workflow.steps, product_id) if workflow else [],
            "case_fields": {
                key: {"label": labels.get(key, key), "value": value}
                for key, value in values.items()
            },
            "legacy": legacy,
        },
    )
    return snapshot


def clone_case_workflow(source, target):
    workflow = CaseWorkflow.objects.filter(case=source).first()
    if not workflow:
        return
    source_product = source.category.product_id
    target_product = target.category.product_id
    steps = deepcopy(workflow.steps)
    values = deepcopy(workflow.custom_values)
    if source_product != target_product:
        steps = [
            {key: step.get(key, "") for key in ("action", "expected", "reference")}
            for step in resolve_steps(steps, source_product)
        ]
        source_fields = {
            field.key: field
            for field in CustomField.objects.filter(
                product_id=source_product, entity="case"
            )
        }
        target_fields = {
            field.key: field
            for field in CustomField.objects.filter(
                product_id=target_product, entity="case"
            )
        }
        values = {
            key: value
            for key, value in values.items()
            if key in target_fields
            and key in source_fields
            and target_fields[key].kind == source_fields[key].kind
            and (
                target_fields[key].kind != "select"
                or value in target_fields[key].choices
            )
        }
    # A clone is a draft: newly required target fields can be completed in the editor.
    CaseWorkflow.objects.create(case=target, steps=steps, custom_values=values)


@transaction.atomic
def record_result(
    user,
    execution_id,
    *,
    status,
    comment="",
    elapsed_seconds=None,
    defects="",
    step_values=None,
    custom_values=None,
):
    execution = (
        TestExecution.objects.select_for_update()
        .select_related("run", "case__category")
        .get(pk=execution_id)
    )
    require(user, "testruns.view_testrun", execution.run)
    require(user, "testruns.view_testexecution", execution)
    require(user, "testruns.change_testexecution", execution)
    require(user, "workflow.add_executionresult")
    if execution.run.stop_date:
        raise ValidationError(_("This run is closed. Reopen it before adding results."))
    if (
        not isinstance(status, TestExecutionStatus)
        or not TestExecutionStatus.objects.filter(pk=status.pk).exists()
    ):
        raise ValidationError(_("Invalid execution status."))
    if elapsed_seconds is not None and (
        type(elapsed_seconds) is not int or not 0 <= elapsed_seconds <= 604800
    ):
        raise ValidationError(_("Elapsed time must be between 0 and 604800 seconds."))
    if (
        not isinstance(comment, str)
        or len(comment) > 50000
        or not isinstance(defects, str)
        or len(defects) > 2000
    ):
        raise ValidationError(_("Comment or defect references are too long."))
    custom_values = {} if custom_values is None else custom_values
    validate_custom_values(execution.case.category.product_id, "result", custom_values)
    snapshot = snapshot_execution(execution, legacy=True)
    step_values = [] if step_values is None else step_values
    if not isinstance(step_values, list) or len(step_values) != len(snapshot.steps):
        raise ValidationError(
            _("Submit a result for every step in the execution snapshot.")
        )
    statuses = {item.pk: item for item in TestExecutionStatus.objects.all()}
    step_results = []
    for step, value in zip(snapshot.steps, step_values):
        if (
            not isinstance(value, dict)
            or set(value) - {"status", "actual"}
            or type(value.get("status")) is not int
            or value["status"] not in statuses
            or not isinstance(value.get("actual", ""), str)
            or len(value.get("actual", "")) > 10000
        ):
            raise ValidationError(_("Invalid step result."))
        step_status = statuses[value["status"]]
        step_results.append(
            {
                **deepcopy(step),
                "status_id": step_status.pk,
                "status_label": str(step_status.name),
                "status_weight": step_status.weight,
                "actual": value.get("actual", ""),
            }
        )
    if status.weight > 0 and any(item["status_weight"] <= 0 for item in step_results):
        raise ValidationError(_("A passed result requires every step to pass."))
    labels = {
        field.key: field.label
        for field in CustomField.objects.filter(
            product_id=execution.case.category.product_id, entity="result"
        )
    }
    result = ExecutionResult.objects.create(
        execution=execution,
        author=user,
        status=status,
        status_label=str(status.name),
        status_weight=status.weight,
        comment=comment,
        elapsed_seconds=elapsed_seconds,
        defects=defects,
        step_results=step_results,
        custom_values={
            key: {"label": labels[key], "value": value}
            for key, value in custom_values.items()
        },
    )
    now = timezone.now()
    execution.status = status
    execution.tested_by = user
    execution.start_date = (
        (now - timedelta(seconds=elapsed_seconds))
        if elapsed_seconds is not None
        else (execution.start_date or now)
    )
    execution.stop_date = now if status.weight != 0 else None
    execution._history_user = user
    execution.save()
    return result


@transaction.atomic
def link_run(user, cycle, run):
    cycle = TestCycle.objects.select_for_update().get(pk=cycle.pk)
    require(user, "workflow.change_testcycle", cycle)
    require(user, "testruns.view_testrun", run)
    require(user, "testruns.change_testrun", run)
    if cycle.is_completed or (
        cycle.milestone_id and cycle.milestone.status == "completed"
    ):
        raise ValidationError(_("Cannot add runs to a completed cycle or milestone."))
    if cycle.product_id != run.plan.product_id:
        raise ValidationError(_("Run belongs to another product."))
    existing = CycleRun.objects.filter(run=run).first()
    if existing and existing.cycle_id != cycle.pk:
        raise ValidationError(_("Run already belongs to another cycle."))
    milestone_link = RunMilestone.objects.filter(run=run).first()
    if milestone_link and milestone_link.milestone_id != cycle.milestone_id:
        raise ValidationError(_("Run is already assigned to another milestone."))
    CycleRun.objects.get_or_create(cycle=cycle, run=run)
    if cycle.milestone_id:
        RunMilestone.objects.get_or_create(run=run, milestone=cycle.milestone)


@transaction.atomic
def create_configuration_runs(user, cycle, plan, build, environments):
    cycle = TestCycle.objects.select_for_update().get(pk=cycle.pk)
    require(user, "workflow.change_testcycle", cycle)
    require(user, "testruns.add_testrun")
    require(user, "testruns.add_testexecution")
    require(user, "testplans.view_testplan", plan)
    require(user, "management.view_build", build)
    if (
        plan.product_id != cycle.product_id
        or build.version_id != plan.product_version_id
        or not build.is_active
    ):
        raise ValidationError(
            _("Select an active build for this plan's version and product.")
        )
    if cycle.is_completed or (
        cycle.milestone_id and cycle.milestone.status == "completed"
    ):
        raise ValidationError(_("Cycle or milestone is completed."))
    cases = confirmed_tree_cases(user, plan)
    if not cases:
        raise ValidationError(_("The plan has no confirmed cases."))
    for case in cases:
        require(user, "testcases.view_testcase", case)
        if case.category.product_id != cycle.product_id:
            raise ValidationError(_("A selected case belongs to another product."))
    selected_environments = list(environments)
    if len(selected_environments) > 30:
        raise ValidationError(_("Select at most 30 configurations at once."))
    for environment in selected_environments:
        require(user, "testruns.view_environment", environment)
    runs = []
    for environment in selected_environments or [None]:
        suffix = f" [{environment.name}]" if environment else ""
        run = TestRun.objects.create(
            summary=f"{cycle.name}: {plan.name}{suffix}"[:255],
            plan=plan,
            build=build,
            manager=user,
            default_tester=user,
        )
        for prop in (
            EnvironmentProperty.objects.filter(environment=environment)
            if environment
            else []
        ):
            run.property_set.create(name=prop.name, value=prop.value)
        for index, case in enumerate(cases):
            run.create_execution(case, assignee=user, sortkey=(index + 1) * 10)
        # Newly created objects are covered by their global add permission.
        CycleRun.objects.create(cycle=cycle, run=run)
        if cycle.milestone_id:
            RunMilestone.objects.create(run=run, milestone=cycle.milestone)
        runs.append(run)
    return runs


@transaction.atomic
def assign_run(user, run, milestone=None, cycle=None):
    run = TestRun.objects.select_for_update().select_related("plan").get(pk=run.pk)
    require(user, "testruns.change_testrun", run)
    product_id = run.plan.product_id
    if milestone:
        require(user, "workflow.view_milestone", milestone)
        if milestone.product_id != product_id or milestone.status == "completed":
            raise ValidationError(
                _("Choose an unfinished milestone of the run's product.")
            )
    old_cycle = CycleRun.objects.filter(run=run).select_related("cycle").first()
    if old_cycle and (not cycle or old_cycle.cycle_id != cycle.pk):
        require(user, "workflow.change_testcycle", old_cycle.cycle)
    if cycle:
        require(user, "workflow.change_testcycle", cycle)
        if cycle.product_id != product_id or cycle.is_completed:
            raise ValidationError(_("Choose an unfinished cycle of the run's product."))
        if cycle.milestone_id != (milestone.pk if milestone else None):
            raise ValidationError(_("Run milestone must match its cycle milestone."))
    CycleRun.objects.filter(run=run).delete()
    RunMilestone.objects.filter(run=run).delete()
    if cycle:
        CycleRun.objects.create(run=run, cycle=cycle)
    if milestone:
        RunMilestone.objects.create(run=run, milestone=milestone)


def progress(executions):
    counts = executions.aggregate(
        total=Count("pk"),
        passed=Count("pk", filter=Q(status__weight__gt=0)),
        failed=Count("pk", filter=Q(status__weight__lt=0)),
        untested=Count("pk", filter=Q(status__weight=0)),
    )
    counts["completed"] = counts["passed"] + counts["failed"]
    counts["percent"] = (
        round(100 * counts["completed"] / counts["total"], 1) if counts["total"] else 0
    )
    return counts
