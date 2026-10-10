import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from tcms.management.models import Product
from tcms.testcases.models import TestCase
from tcms.testruns.models import TestExecutionStatus

from . import forms
from .models import CaseWorkflow, CustomField, Milestone, SharedStepSet, TestCycle
from .services import (
    allowed,
    assign_run,
    create_configuration_runs,
    link_run,
    progress,
    record_result,
    require,
    resolve_steps,
    snapshot_execution,
    visible,
    visible_executions,
    visible_runs,
)


def show_error(form, error):
    form.add_error(None, ValidationError(error.messages))


def product_initial(request):
    value = request.GET.get("product")
    return {"product": value} if value and value.isdecimal() else {}


@login_required
def hub(request):
    products = visible(request.user, Product, "management.view_product")
    product_id = request.GET.get("product")
    if product_id:
        product = (
            get_object_or_404(products, pk=product_id)
            if product_id.isdecimal()
            else None
        )
        if product is None:
            return HttpResponse("Invalid product", status=400)
        products_filter = products.filter(pk=product.pk)
    else:
        product = None
        products_filter = products
    return render(
        request,
        "workflow/hub.html",
        {
            "products": products,
            "product": product,
            "milestones": visible(request.user, Milestone, "workflow.view_milestone")
            .filter(product__in=products_filter)
            .select_related("product")[:100],
            "cycles": visible(request.user, TestCycle, "workflow.view_testcycle")
            .filter(product__in=products_filter)
            .select_related("product", "milestone")[:100],
            "libraries": visible(
                request.user, SharedStepSet, "workflow.view_sharedstepset"
            )
            .filter(product__in=products_filter)
            .select_related("product")[:100],
            "fields": visible(request.user, CustomField, "workflow.view_customfield")
            .filter(product__in=products_filter)
            .select_related("product")[:100],
        },
    )


def edit_entity(request, model, form_class, pk=None):
    name = model._meta.model_name
    obj = (
        get_object_or_404(visible(request.user, model, f"workflow.view_{name}"), pk=pk)
        if pk
        else None
    )
    require(
        request.user, f"workflow.change_{name}" if pk else f"workflow.add_{name}", obj
    )
    form = form_class(
        request.POST if request.method == "POST" else None,
        user=request.user,
        instance=obj,
        initial=product_initial(request),
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, "Saved")
        if hasattr(obj, "get_absolute_url"):
            return redirect(obj.get_absolute_url())
        return redirect(f"/workflow/?product={obj.product_id}")
    return render(
        request,
        "workflow/form.html",
        {
            "form": form,
            "title": f"{'Edit' if pk else 'New'} {model._meta.verbose_name}",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def milestone_edit(request, pk=None):
    return edit_entity(request, Milestone, forms.MilestoneForm, pk)


@login_required
def milestone_detail(request, pk):
    obj = get_object_or_404(
        visible(request.user, Milestone, "workflow.view_milestone"), pk=pk
    )
    runs = visible_runs(request.user).filter(milestone_link__milestone=obj)
    executions = visible_executions(request.user).filter(run__in=runs)
    return render(
        request,
        "workflow/milestone.html",
        {
            "object": obj,
            "runs": runs[:100],
            "stats": progress(executions),
            "cycles": visible(
                request.user, TestCycle, "workflow.view_testcycle"
            ).filter(milestone=obj),
            "children": visible(
                request.user, Milestone, "workflow.view_milestone"
            ).filter(parent=obj),
            "can_edit": allowed(request.user, "workflow.change_milestone", obj),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def cycle_edit(request, pk=None):
    return edit_entity(request, TestCycle, forms.CycleForm, pk)


@login_required
@require_http_methods(["GET", "POST"])
def cycle_detail(request, pk):
    obj = get_object_or_404(
        visible(request.user, TestCycle, "workflow.view_testcycle"), pk=pk
    )
    creating = request.method == "POST" and request.POST.get("action") == "create"
    linking = request.method == "POST" and request.POST.get("action") == "link"
    create_form = forms.ConfigurationRunForm(
        request.POST if creating else None,
        user=request.user,
        cycle=obj,
        prefix="create",
    )
    link_form = forms.LinkRunForm(
        request.POST if linking else None, user=request.user, cycle=obj, prefix="link"
    )
    if request.method == "POST":
        require(request.user, "workflow.change_testcycle", obj)
        try:
            if creating and create_form.is_valid():
                created = create_configuration_runs(
                    request.user, obj, **create_form.cleaned_data
                )
                messages.success(request, f"Created {len(created)} run(s)")
                return redirect(obj)
            if linking and link_form.is_valid():
                link_run(request.user, obj, link_form.cleaned_data["run"])
                return redirect(obj)
            if not (creating or linking):
                return HttpResponse("Invalid action", status=400)
        except ValidationError as error:
            show_error(create_form if creating else link_form, error)
    runs = visible_runs(request.user).filter(test_cycles=obj)
    return render(
        request,
        "workflow/cycle.html",
        {
            "object": obj,
            "runs": runs[:100],
            "stats": progress(visible_executions(request.user).filter(run__in=runs)),
            "create_form": create_form,
            "link_form": link_form,
            "can_edit": allowed(request.user, "workflow.change_testcycle", obj),
            "can_create": allowed(request.user, "testruns.add_testrun")
            and allowed(request.user, "testruns.add_testexecution"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def shared_edit(request, pk=None):
    obj = (
        get_object_or_404(
            visible(request.user, SharedStepSet, "workflow.view_sharedstepset"), pk=pk
        )
        if pk
        else None
    )
    require(
        request.user,
        "workflow.change_sharedstepset" if pk else "workflow.add_sharedstepset",
        obj,
    )
    form = forms.SharedStepForm(
        request.POST if request.method == "POST" else None,
        user=request.user,
        instance=obj,
        initial=product_initial(request),
    )
    steps = forms.StepFormSet(
        request.POST if request.method == "POST" else None,
        prefix="steps",
        initial=forms.step_initial(obj.steps if obj else []),
        form_kwargs={
            "product_id": obj.product_id if obj else None,
            "shared_allowed": False,
        },
    )
    if request.method == "POST":
        valid = form.is_valid() & steps.is_valid()
        if valid:
            obj = form.save(commit=False)
            obj.steps = steps.as_steps()
            try:
                if not obj.steps:
                    raise ValidationError("Add at least one shared step.")
                obj.full_clean()
                obj.save()
                return redirect(f"/workflow/?product={obj.product_id}")
            except ValidationError as error:
                show_error(form, error)
    return render(
        request,
        "workflow/editor.html",
        {"form": form, "steps": steps, "title": "Shared steps", "can_edit": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def field_edit(request, pk=None):
    return edit_entity(request, CustomField, forms.CustomFieldForm, pk)


@login_required
def shared_detail(request, pk):
    obj = get_object_or_404(
        visible(request.user, SharedStepSet, "workflow.view_sharedstepset"), pk=pk
    )
    return render(
        request,
        "workflow/editor.html",
        {
            "title": obj.name,
            "library": obj,
            "resolved": obj.steps,
            "can_edit": False,
            "can_change": allowed(request.user, "workflow.change_sharedstepset", obj),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def case_detail(request, pk):
    case = get_object_or_404(
        visible(request.user, TestCase, "testcases.view_testcase").select_related(
            "category"
        ),
        pk=pk,
    )
    workflow = CaseWorkflow.objects.filter(case=case).first()
    can_edit = allowed(request.user, "testcases.change_testcase", case)
    product_id = case.category.product_id
    steps = forms.StepFormSet(
        request.POST if request.method == "POST" else None,
        prefix="steps",
        initial=forms.step_initial(workflow.steps if workflow else []),
        form_kwargs={"product_id": product_id, "user": request.user},
    )
    custom = forms.CustomValuesForm(
        request.POST if request.method == "POST" else None,
        product_id=product_id,
        entity="case",
        values=workflow.custom_values if workflow else {},
    )
    error_text = None
    if request.method == "POST":
        require(request.user, "testcases.change_testcase", case)
        valid = steps.is_valid() & custom.is_valid()
        if valid:
            try:
                with transaction.atomic():
                    TestCase.objects.select_for_update().get(pk=case.pk)
                    workflow, _ = CaseWorkflow.objects.get_or_create(case=case)
                    workflow.steps = steps.as_steps()
                    workflow.custom_values = custom.values(workflow.custom_values)
                    workflow.full_clean()
                    workflow._history_user = request.user
                    workflow.save()
                messages.success(
                    request,
                    "Steps and custom fields saved; existing execution snapshots are preserved",
                )
                return redirect("workflow:case", pk=case.pk)
            except ValidationError as error:
                error_text = " ".join(error.messages)
                workflow = CaseWorkflow.objects.filter(case=case).first()
    resolved = resolve_steps(workflow.steps, product_id) if workflow else []
    return render(
        request,
        "workflow/editor.html",
        {
            "case": case,
            "title": f"TC-{case.pk}: {case.summary}",
            "steps": steps,
            "custom": custom,
            "can_edit": can_edit,
            "resolved": resolved,
            "error_text": error_text,
            "custom_values": workflow.custom_values if workflow else {},
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def execution_detail(request, pk):
    execution = get_object_or_404(
        visible_executions(request.user).select_related(
            "case__category", "run", "status"
        ),
        pk=pk,
    )
    snapshot = snapshot_execution(execution, legacy=True)
    can_edit = allowed(
        request.user, "testruns.change_testexecution", execution
    ) and allowed(request.user, "workflow.add_executionresult")
    form = forms.ResultForm(request.POST if request.method == "POST" else None)
    custom = forms.CustomValuesForm(
        request.POST if request.method == "POST" else None,
        product_id=execution.case.category.product_id,
        entity="result",
    )
    idle = TestExecutionStatus.objects.filter(weight=0).first()
    step_results = forms.StepResultFormSet(
        request.POST if request.method == "POST" else None,
        prefix="results",
        initial=[{"status": idle.pk if idle else None} for _ in snapshot.steps],
    )
    if request.method == "POST":
        require(request.user, "testruns.change_testexecution", execution)
        require(request.user, "workflow.add_executionresult")
        valid = form.is_valid() & step_results.is_valid() & custom.is_valid()
        if valid:
            try:
                record_result(
                    request.user,
                    execution.pk,
                    **form.cleaned_data,
                    step_values=[
                        {
                            "status": row.cleaned_data["status"].pk,
                            "actual": row.cleaned_data["actual"],
                        }
                        for row in step_results
                    ],
                    custom_values=custom.values(),
                )
                messages.success(request, "Result added")
                return redirect("workflow:execution", pk=execution.pk)
            except ValidationError as error:
                show_error(form, error)
    return render(
        request,
        "workflow/execution.html",
        {
            "execution": execution,
            "snapshot": snapshot,
            "form": form,
            "custom": custom,
            "step_results": step_results,
            "step_rows": list(zip(snapshot.steps, step_results.forms)),
            "attempts": execution.results.select_related("author"),
            "can_edit": can_edit,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def run_detail(request, pk):
    run = get_object_or_404(visible_runs(request.user), pk=pk)
    milestone_link = getattr(run, "milestone_link", None)
    cycle_link = getattr(run, "cycle_link", None)
    form = forms.RunPlanningForm(
        request.POST if request.method == "POST" else None,
        user=request.user,
        run=run,
        initial={
            "milestone": milestone_link.milestone_id if milestone_link else None,
            "cycle": cycle_link.cycle_id if cycle_link else None,
        },
    )
    if request.method == "POST":
        require(request.user, "testruns.change_testrun", run)
        if form.is_valid():
            try:
                assign_run(request.user, run, **form.cleaned_data)
                return redirect("workflow:run", pk=run.pk)
            except ValidationError as error:
                show_error(form, error)
    executions = (
        visible_executions(request.user)
        .filter(run=run)
        .select_related("case", "status", "assignee")
    )
    stats = progress(executions)
    group = request.GET.get("status", "all")
    if group == "passed":
        executions = executions.filter(status__weight__gt=0)
    elif group == "failed":
        executions = executions.filter(status__weight__lt=0)
    elif group == "untested":
        executions = executions.filter(status__weight=0)
    if request.GET.get("assigned") == "me":
        executions = executions.filter(assignee=request.user)
    return render(
        request,
        "workflow/run.html",
        {
            "run": run,
            "executions": executions.order_by("sortkey", "pk")[:1000],
            "stats": stats,
            "form": form,
            "can_edit": allowed(request.user, "testruns.change_testrun", run),
        },
    )


@login_required
def todo(request):
    executions = visible_executions(request.user).filter(
        assignee=request.user, status__weight__lte=0, run__stop_date__isnull=True
    )
    return render(
        request,
        "workflow/todo.html",
        {
            "executions": executions.select_related("case", "run", "status").order_by(
                "run__planned_stop", "run_id", "sortkey", "pk"
            )[:1000],
        },
    )


def csv_value(value):
    value = str(value) if value is not None else ""
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


@login_required
def report(request):
    products = visible(request.user, Product, "management.view_product")
    runs = visible_runs(request.user).filter(plan__product__in=products)
    selected_product = None
    planning_filters = []
    for param, model, permission, lookup in (
        ("product", Product, "management.view_product", "run__plan__product_id"),
        (
            "milestone",
            Milestone,
            "workflow.view_milestone",
            "run__milestone_link__milestone_id",
        ),
        ("cycle", TestCycle, "workflow.view_testcycle", "run__test_cycles__pk"),
    ):
        value = request.GET.get(param)
        if value:
            if not value.isdecimal():
                return HttpResponse("Invalid filter", status=400)
            obj = get_object_or_404(visible(request.user, model, permission), pk=value)
            if param == "product":
                selected_product = obj
            else:
                planning_filters.append({"param": param, "object": obj})
            run_lookup = lookup.removeprefix("run__")
            runs = runs.filter(**{run_lookup: obj.pk})
    executions = visible_executions(request.user).filter(run__in=runs)
    stats = progress(executions)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="kiwi-results.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(
            [
                "Run ID",
                "Run",
                "Execution ID",
                "Case ID",
                "Case",
                "Requirement",
                "Status",
                "Assignee",
                "Tested by",
                "Elapsed seconds",
                "Comment",
                "Defects",
            ]
        )
        for execution in (
            executions.select_related("run", "case", "status", "assignee", "tested_by")
            .prefetch_related("results")
            .order_by("run_id", "sortkey", "pk")
            .iterator(chunk_size=200)
        ):
            result = next(iter(execution.results.all()), None)
            writer.writerow(
                [
                    csv_value(value)
                    for value in (
                        execution.run_id,
                        execution.run.summary,
                        execution.pk,
                        execution.case_id,
                        execution.case.summary,
                        execution.case.requirement,
                        execution.status.name,
                        execution.assignee.username if execution.assignee else "",
                        execution.tested_by.username if execution.tested_by else "",
                        result.elapsed_seconds if result else "",
                        result.comment if result else "",
                        result.defects if result else "",
                    )
                ]
            )
        return response
    breakdown = (
        executions.values("run_id", "run__summary")
        .annotate(
            total=Count("pk"),
            passed=Count("pk", filter=Q(status__weight__gt=0)),
            failed=Count("pk", filter=Q(status__weight__lt=0)),
            untested=Count("pk", filter=Q(status__weight=0)),
        )
        .order_by("run_id")
    )
    return render(
        request,
        "workflow/report.html",
        {
            "planning_filters": planning_filters,
            "products": products,
            "product": selected_product,
            "stats": stats,
            "breakdown": breakdown[:1000],
            "csv_query": request.GET.copy().urlencode(),
        },
    )
