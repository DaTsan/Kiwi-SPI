import csv
import io

from django.test import Client
from django.urls import reverse
from django.utils import timezone
from guardian.shortcuts import assign_perm

from tcms.tests.factories import TestExecutionFactory, TestRunFactory
from tcms.workflow.models import (
    CaseWorkflow,
    CustomField,
    Milestone,
    SharedStepSet,
    TestCycle,
)
from tcms.workflow.services import assign_run, record_result

from .base import WorkflowTestCase


class WorkflowViewsTests(WorkflowTestCase):
    def setUp(self):
        self.client.force_login(self.user)

    def test_all_workflow_pages_render(self):
        shared = SharedStepSet.objects.create(
            product=self.product, name="Login", steps=[{"action": "Log in"}]
        )
        field = self.field()
        routes = [
            ("hub", []),
            ("milestone-new", []),
            ("milestone", [self.milestone.pk]),
            ("milestone-edit", [self.milestone.pk]),
            ("cycle-new", []),
            ("cycle", [self.cycle.pk]),
            ("cycle-edit", [self.cycle.pk]),
            ("shared-new", []),
            ("shared", [shared.pk]),
            ("shared-edit", [shared.pk]),
            ("field-new", []),
            ("field-edit", [field.pk]),
            ("case", [self.case.pk]),
            ("execution", [self.execution.pk]),
            ("run", [self.test_run.pk]),
            ("todo", []),
            ("report", []),
        ]
        for route, args in routes:
            with self.subTest(route=route):
                self.assertEqual(
                    self.client.get(
                        reverse(f"workflow:{route}", args=args)
                    ).status_code,
                    200,
                )

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("workflow:hub")).status_code, 302)

    def test_create_milestone_then_cycle(self):
        response = self.client.post(
            reverse("workflow:milestone-new"),
            {
                "product": self.product.pk,
                "name": "Release 2",
                "status": "open",
                "start_date": "2026-10-11",
                "due_date": "2026-11-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        milestone = Milestone.objects.get(name="Release 2")
        response = self.client.post(
            reverse("workflow:cycle-new"),
            {"product": self.product.pk, "name": "Smoke", "milestone": milestone.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TestCycle.objects.get(name="Smoke").milestone, milestone)

    def test_edit_structured_case_and_custom_fields(self):
        self.field("risk", "select", choices=["High", "Low"], required=True)
        shared = SharedStepSet.objects.create(
            product=self.product, name="Login", steps=[{"action": "Log in"}]
        )
        data = self.step_post(
            [
                {"action": "Check home", "expected": "Welcome", "ORDER": 2},
                {"shared": shared.pk, "ORDER": 1},
            ]
        )
        data["custom_risk"] = "High"
        response = self.client.post(reverse("workflow:case", args=[self.case.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.steps[0], {"shared_id": shared.pk})
        self.assertEqual(self.workflow.custom_values, {"risk": "High"})
        self.assertEqual(
            self.execution.workflow_snapshot.steps[0]["action"], "Open login"
        )

    def test_invalid_case_form_does_not_overwrite_saved_steps(self):
        data = self.step_post([{"action": "", "ORDER": 1}])
        response = self.client.post(reverse("workflow:case", args=[self.case.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.steps[0]["action"], "Open login")

    def test_create_shared_steps_then_reuse(self):
        data = self.step_post(
            [{"action": "Authenticate", "expected": "Session", "ORDER": 1}]
        )
        data.update({"product": self.product.pk, "name": "Authentication"})
        response = self.client.post(reverse("workflow:shared-new"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            SharedStepSet.objects.get(name="Authentication").steps[0]["action"],
            "Authenticate",
        )

    def test_create_select_field_from_lines(self):
        response = self.client.post(
            reverse("workflow:field-new"),
            {
                "product": self.product.pk,
                "entity": "case",
                "key": "risk",
                "label": "Risk",
                "kind": "select",
                "choices": "High\nLow",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomField.objects.get(key="risk").choices, ["High", "Low"])

    def test_cycle_configuration_post_creates_run(self):
        response = self.client.post(
            reverse("workflow:cycle", args=[self.cycle.pk]),
            {
                "action": "create",
                "create-plan": self.plan.pk,
                "create-build": self.build.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.cycle.runs.count(), 1)

    def test_submit_result_and_render_history(self):
        data = self.step_post(
            [{"status": self.passed.pk, "actual": "Welcome"}], prefix="results"
        )
        data.update(
            {
                "status": self.passed.pk,
                "comment": "Completed",
                "elapsed_seconds": "15",
                "defects": "BUG-12",
            }
        )
        url = reverse("workflow:execution", args=[self.execution.pk])
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(url), "Completed")
        self.assertEqual(self.execution.results.get().elapsed_seconds, 15)

    def test_script_text_is_escaped_in_scenarios_and_results(self):
        self.workflow.steps = [{"action": '<script>alert("x")</script>'}]
        self.workflow.save()
        response = self.client.get(reverse("workflow:case", args=[self.case.pk]))
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        record_result(
            self.user,
            self.execution.pk,
            status=self.failed,
            comment="<script>attack()</script>",
            step_values=self.step_values(self.failed),
        )
        response = self.client.get(
            reverse("workflow:execution", args=[self.execution.pk])
        )
        self.assertNotContains(response, "<script>attack()</script>")
        self.assertContains(response, "&lt;script&gt;attack()&lt;/script&gt;")

    def test_csrf_is_required_for_writes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            reverse("workflow:case", args=[self.case.pk]), self.step_post([])
        )
        self.assertEqual(response.status_code, 403)

    def test_restricted_user_cannot_see_objects_or_modify_cases(self):
        user = self.restricted_user()
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse("workflow:case", args=[self.case.pk])).status_code,
            404,
        )
        assign_perm("testcases.view_testcase", user, self.case)
        self.assertEqual(
            self.client.get(reverse("workflow:case", args=[self.case.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                reverse("workflow:case", args=[self.case.pk]), self.step_post([])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("workflow:milestone", args=[self.milestone.pk])
            ).status_code,
            404,
        )

    def test_hidden_run_excluded_from_report_even_with_execution_permission(self):
        user = self.restricted_user()
        assign_perm("management.view_product", user, self.product)
        assign_perm("testruns.view_testexecution", user)
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(
                reverse("workflow:execution", args=[self.execution.pk])
            ).status_code,
            404,
        )
        response = self.client.get(reverse("workflow:report"), {"format": "csv"})
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        assign_perm("testruns.view_testrun", user, self.test_run)
        response = self.client.get(reverse("workflow:report"), {"format": "csv"})
        self.assertEqual(
            len(list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))), 2
        )

    def test_csv_escapes_formulas_and_obeys_planning_filters(self):
        self.case.summary = '=HYPERLINK("https://example.com")'
        self.case.save()
        assign_run(self.user, self.test_run, milestone=self.milestone, cycle=self.cycle)
        record_result(
            self.user,
            self.execution.pk,
            status=self.failed,
            comment="  +formula",
            step_values=self.step_values(self.failed),
        )
        response = self.client.get(
            reverse("workflow:report"),
            {"format": "csv", "milestone": self.milestone.pk, "cycle": self.cycle.pk},
        )
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][4].startswith("'="))
        self.assertTrue(rows[1][10].startswith("'  +"))
        response = self.client.get(
            reverse("workflow:report"), {"milestone": self.milestone.pk}
        )
        self.assertEqual(response.context["stats"]["failed"], 1)
        self.assertEqual(response.context["stats"]["percent"], 100)
        self.assertContains(response, f'name="milestone" value="{self.milestone.pk}"')
        response = self.client.get(reverse("workflow:report"), {"cycle": self.cycle.pk})
        self.assertContains(response, f'name="cycle" value="{self.cycle.pk}"')
        self.assertContains(response, "Regression")

    def test_todo_shows_only_my_pending_open_executions(self):
        other_user = self.restricted_user()
        foreign = self.test_run.create_execution(self.case, assignee=other_user)[0]
        passed = self.test_run.create_execution(self.case, assignee=self.user)[0]
        record_result(
            self.user, passed.pk, status=self.passed, step_values=self.step_values()
        )
        closed_run = TestRunFactory(
            plan=self.plan, build=self.build, stop_date=timezone.now()
        )
        closed = closed_run.create_execution(self.case, assignee=self.user)[0]
        response = self.client.get(reverse("workflow:todo"))
        ids = [item.pk for item in response.context["executions"]]
        self.assertIn(self.execution.pk, ids)
        for execution in (foreign, passed, closed):
            self.assertNotIn(execution.pk, ids)

    def test_invalid_report_filter_returns_400(self):
        self.assertEqual(
            self.client.get(
                reverse("workflow:report"), {"product": "invalid"}
            ).status_code,
            400,
        )

    def test_admin_history_does_not_expose_hidden_execution(self):
        result = record_result(
            self.user,
            self.execution.pk,
            status=self.failed,
            comment="Private result",
            step_values=self.step_values(self.failed),
        )
        user = self.restricted_user()
        assign_perm("workflow.view_executionresult", user)
        self.client.force_login(user)
        response = self.client.get(reverse("admin:workflow_executionresult_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_count, 0)
        response = self.client.get(
            reverse("admin:workflow_executionresult_change", args=[result.pk])
        )
        self.assertNotContains(response, "Private result", status_code=302)
