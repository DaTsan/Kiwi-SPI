"""Temporary, explicitly tagged fixtures for manual browser QA of this project.

Run inside the local web container with `python local/smoke_workflow.py setup`,
then `verify` after two results have been submitted, and finally `cleanup`.
Only IDs in this container's private manifest and the exact random product
name are eligible for cleanup. No existing product or account is modified.
"""
import csv
import io
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django

django.setup()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import RequestFactory

from tcms.management.models import Classification, Priority, Product
from tcms.testcases.models import TestCase, TestCaseStatus
from tcms.testplans.models import PlanType, TestPlan
from tcms.testruns.models import Environment, EnvironmentProperty, TestRun
from tcms.workflow.models import CaseWorkflow, CustomField, Milestone, SharedStepSet, TestCycle
from tcms.workflow.views import report

MANIFEST = Path("/tmp/kiwi-workflow-smoke.json")


def setup():
    if MANIFEST.exists():
        raise RuntimeError("Clean up the previous fixture first")
    tag = "Workflow QA " + uuid.uuid4().hex[:12]
    user = get_user_model().objects.get(username=os.environ["KIWI_ADMIN_USERNAME"])
    with transaction.atomic():
        classification = Classification.objects.create(name=tag)
        plan_type = PlanType.objects.create(name=tag)
        product = Product.objects.create(name=tag, classification=classification)
        version = product.version.first()
        plan = TestPlan.objects.create(name="Browser regression", product=product, product_version=version, author=user, type=plan_type)
        case = TestCase.objects.create(summary="Login workflow", category=product.category.first(), case_status=TestCaseStatus.objects.filter(is_confirmed=True).first(), priority=Priority.objects.first(), author=user, reviewer=user, default_tester=user, text="Browser QA fixture", requirement="REQ-QA-1")
        plan.add_case(case, 10)
        shared = SharedStepSet.objects.create(product=product, name="Check session", steps=[{"action": "Check active session", "expected": "Session is active"}])
        CaseWorkflow.objects.create(case=case, steps=[{"action": "Open login", "expected": "Login page"}, {"shared_id": shared.pk}], custom_values={"risk": "High"})
        CustomField.objects.create(product=product, entity="case", key="risk", label="Risk", kind="select", choices=["High", "Low"], required=True)
        CustomField.objects.create(product=product, entity="result", key="release_url", label="Release URL", kind="url", required=True)
        milestone = Milestone.objects.create(product=product, name="QA release")
        cycle = TestCycle.objects.create(product=product, milestone=milestone, name="Browser cycle")
        environments = []
        for browser in ("Chrome", "Firefox"):
            environment = Environment.objects.create(name=f"{tag} {browser}")
            EnvironmentProperty.objects.create(environment=environment, name="browser", value=browser)
            environments.append(environment.pk)
        manifest = {"product": product.pk, "name": tag, "classification": classification.pk, "plan_type": plan_type.pk, "plan": plan.pk, "build": version.build.first().pk, "case": case.pk, "shared": shared.pk, "milestone": milestone.pk, "cycle": cycle.pk, "environments": environments}
    MANIFEST.write_text(json.dumps(manifest))
    print(json.dumps(manifest))


def fixture():
    manifest = json.loads(MANIFEST.read_text())
    product = Product.objects.get(pk=manifest["product"], name=manifest["name"])
    if not product.name.startswith("Workflow QA "):
        raise RuntimeError("Not a QA fixture")
    return manifest, product


def verify():
    manifest, product = fixture()
    cycle = TestCycle.objects.get(pk=manifest["cycle"], product=product)
    assert cycle.runs.count() == 2, "Expected two configuration runs"
    executions = list(cycle.runs.first().executions.all())
    assert len(executions) == 1
    execution = executions[0]
    if execution.results.count() != 2:
        execution = cycle.runs.last().executions.get()
    assert execution.results.count() == 2, "Expected two browser-submitted attempts"
    assert execution.status.weight > 0
    assert len(execution.workflow_snapshot.steps) == 3
    assert execution.workflow_snapshot.steps[0]["action"] == "Enter credentials"
    assert execution.results.first().custom_values["release_url"]["value"] == "https://example.com/build/42"
    shared = SharedStepSet.objects.get(pk=manifest["shared"], product=product)
    shared.steps = [{"action": "Changed after execution"}]
    shared.save()
    execution.workflow_snapshot.refresh_from_db()
    assert execution.workflow_snapshot.steps[-1]["action"] == "Check active session"
    request = RequestFactory().get("/workflow/reports/", {"cycle": cycle.pk, "format": "csv"})
    request.user = get_user_model().objects.get(username=os.environ["KIWI_ADMIN_USERNAME"])
    response = report(request)
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 3
    assert any("Second attempt: fix verified" in row for row in rows[1:])
    print(json.dumps({"ok": True, "database": "MariaDB", "runs": 2, "attempts": 2, "steps": 3, "csv_rows": 2, "execution": execution.pk}))


def cleanup():
    manifest, product = fixture()
    with transaction.atomic():
        # Remove only history for objects owned by this exact fixture.
        history_ids = []
        for model in apps.get_models():
            if not hasattr(model, "history"):
                continue
            names = {field.name for field in model._meta.fields}
            if model == Product:
                objects = model.objects.filter(pk=product.pk)
            elif "product" in names:
                objects = model.objects.filter(product=product)
            elif model == TestRun:
                objects = model.objects.filter(plan__product=product)
            elif model == TestCase:
                objects = model.objects.filter(category__product=product)
            elif model == CaseWorkflow:
                objects = model.objects.filter(case__category__product=product)
            elif model._meta.label_lower == "testruns.testexecution":
                objects = model.objects.filter(run__plan__product=product)
            else:
                continue
            history_ids.append((model, list(objects.values_list("pk", flat=True))))
        TestRun.objects.filter(plan__product=product).delete()
        TestCycle.objects.filter(product=product).delete()
        Milestone.objects.filter(product=product).delete()
        product.delete()
        Environment.objects.filter(pk__in=manifest["environments"], name__startswith=manifest["name"] + " ").delete()
        for model, ids in history_ids:
            model.history.filter(id__in=ids).delete()
        Classification.objects.filter(pk=manifest["classification"], name=manifest["name"]).delete()
        PlanType.objects.filter(pk=manifest["plan_type"], name=manifest["name"]).delete()
    MANIFEST.unlink()
    print("QA fixture removed")


{"setup": setup, "verify": verify, "cleanup": cleanup}[sys.argv[1]]()
