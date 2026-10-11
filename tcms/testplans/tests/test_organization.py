"""Case organization must preserve memberships, permissions and execution history."""

import json
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse
from guardian.shortcuts import assign_perm

from tcms.testcases.models import Property, TestCase, TestCasePlan
from tcms.testplans.models import TestPlan
from tcms.testruns.models import TestRun
from tcms.tests.factories import (
    CategoryFactory,
    ComponentFactory,
    TagFactory,
    TestCaseFactory,
    TestPlanFactory,
)
from tcms.workflow.models import CaseWorkflow, ExecutionResult, SharedStepSet
from tcms.workflow.services import (
    create_configuration_runs,
    record_result,
    snapshot_execution,
)
from tcms.workflow.tests.base import WorkflowTestCase


class OrganizationTests(WorkflowTestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("plan-case-organization", args=[self.plan.pk])
        self.child = self.section()
        self.second = TestCaseFactory(category=self.case.category)
        self.plan.add_case(self.second, 20)

    def section(self, parent=None, **kwargs):
        return TestPlanFactory(
            parent=parent or self.plan,
            product=self.product,
            product_version=self.version,
            type=self.plan.type,
            **kwargs,
        )

    def post(self, data, status=200):
        response = self.client.post(self.url, data, content_type="application/json")
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    @staticmethod
    def order(section, previous, cases):
        return {"section": section.pk, "previous": previous, "cases": cases}

    def reorder(self, cases=None, previous=None, status=200):
        return self.post(
            {
                "action": "order",
                "orders": [
                    self.order(
                        self.plan,
                        (
                            previous
                            if previous is not None
                            else [self.case.pk, self.second.pk]
                        ),
                        cases if cases is not None else [self.second.pk, self.case.pk],
                    )
                ],
            },
            status,
        )

    def transfer(self, mode="move", items=None, destination=None, status=200):
        return self.post(
            {
                "action": "transfer",
                "mode": mode,
                "destination": (destination or self.child).pk,
                "items": (
                    items
                    if items is not None
                    else [{"section": self.plan.pk, "case": self.case.pk}]
                ),
            },
            status,
        )

    def ordered(self, section):
        return list(
            TestCasePlan.objects.filter(plan=section)
            .order_by("sortkey", "case_id")
            .values_list("case_id", flat=True)
        )

    def reader(self, *permissions):
        user = self.restricted_user()
        for permission in (
            "testplans.view_testplan",
            "testcases.view_testcase",
            *permissions,
        ):
            assign_perm(permission, user)
        self.client.force_login(user)
        return user

    def test_create_grandchild_inherits_context_and_author(self):
        result = self.post(
            {
                "action": "create",
                "section": self.child.pk,
                "name": "  Подсекция  ",
                "description": "Описание",
            }
        )
        section = TestPlan.objects.get(pk=result["section"])
        self.assertEqual(section.parent_id, self.child.pk)
        self.assertEqual(section.name, "Подсекция")
        self.assertEqual(section.text, "Описание")
        self.assertEqual(section.product_id, self.plan.product_id)
        self.assertEqual(section.product_version_id, self.plan.product_version_id)
        self.assertEqual(section.type_id, self.plan.type_id)
        self.assertEqual(section.author_id, self.user.pk)
        self.assertEqual(section.history.first().history_user_id, self.user.pk)
        self.assertIn(section, self.plan.descendants())

    def test_rename_preserves_hierarchy_description_and_cases(self):
        original = (self.child.parent_id, self.child.text, self.child.author_id)
        self.child.add_case(self.case)
        self.post(
            {
                "action": "rename",
                "section": self.child.pk,
                "name": "Новое имя",
                "description": "Ignored",
            }
        )
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Новое имя")
        self.assertEqual(
            (self.child.parent_id, self.child.text, self.child.author_id), original
        )
        self.assertEqual(self.ordered(self.child), [self.case.pk])

    def test_create_requires_both_add_and_parent_change(self):
        self.reader("testplans.add_testplan")
        before = TestPlan.objects.count()
        self.post(
            {"action": "create", "section": self.plan.pk, "name": "Forbidden"}, 403
        )
        self.assertEqual(TestPlan.objects.count(), before)

    def test_object_parent_permission_grants_new_child_management(self):
        user = self.restricted_user()
        assign_perm("testplans.view_testplan", user, self.plan)
        assign_perm("testplans.change_testplan", user, self.plan)
        assign_perm("testplans.add_testplan", user)
        self.client.force_login(user)
        result = self.post(
            {"action": "create", "section": self.plan.pk, "name": "Child"}
        )
        child = TestPlan.objects.get(pk=result["section"])
        self.assertTrue(user.has_perm("testplans.view_testplan", child))
        self.assertTrue(user.has_perm("testplans.change_testplan", child))
        self.post({"action": "rename", "section": child.pk, "name": "Renamed"})

    def test_cannot_create_or_rename_outside_current_subtree(self):
        sibling = TestPlanFactory(product=self.product, product_version=self.version)
        for action in ("create", "rename"):
            with self.subTest(action=action):
                self.post(
                    {"action": action, "section": sibling.pk, "name": "Wrong"}, 400
                )
        sibling.refresh_from_db()
        self.assertNotEqual(sibling.name, "Wrong")

    def test_invalid_names_do_not_create_sections(self):
        before = TestPlan.objects.count()
        for name in ("", "  ", "x" * 256, None, ["name"]):
            with self.subTest(name=str(name)[:15]):
                self.post(
                    {"action": "create", "section": self.plan.pk, "name": name}, 400
                )
        self.assertEqual(TestPlan.objects.count(), before)

    def test_reorder_persists_and_tree_api_returns_same_order(self):
        self.reorder()
        self.assertEqual(self.ordered(self.plan), [self.second.pk, self.case.pk])
        self.assertEqual(
            list(
                TestCasePlan.objects.filter(plan=self.plan)
                .order_by("sortkey")
                .values_list("sortkey", flat=True)
            ),
            [0, 10],
        )
        response = self.client.post(
            "/json-rpc/",
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "TestPlan.tree",
                    "params": [self.plan.pk, True],
                    "id": 1,
                }
            ),
            content_type="application/json",
        )
        tree = response.json()["result"]
        root = next(section for section in tree if section["id"] == self.plan.pk)
        self.assertEqual(
            [item["case_id"] for item in root["cases"]], [self.second.pk, self.case.pk]
        )

    def test_null_and_tied_sortkeys_have_deterministic_previous_order(self):
        TestCasePlan.objects.filter(plan=self.plan).update(sortkey=None)
        previous = sorted([self.case.pk, self.second.pk])
        self.reorder(cases=list(reversed(previous)), previous=previous)
        self.assertEqual(self.ordered(self.plan), list(reversed(previous)))

    def test_stale_order_returns_conflict_without_overwriting(self):
        self.reorder()
        self.reorder(status=409)
        self.assertEqual(self.ordered(self.plan), [self.second.pk, self.case.pk])

    def test_read_only_user_cannot_reorder(self):
        self.reader()
        self.reorder(status=403)
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])

    def test_object_membership_permissions_allow_reorder(self):
        user = self.reader()
        for link in TestCasePlan.objects.filter(plan=self.plan):
            assign_perm("testcases.change_testcaseplan", user, link)
        self.reorder()
        self.assertEqual(self.ordered(self.plan), [self.second.pk, self.case.pk])

    def test_loss_duplicates_and_unknown_cases_rejected_atomically(self):
        for cases in (
            [self.case.pk],
            [self.case.pk, self.case.pk],
            [self.case.pk, 999999],
        ):
            with self.subTest(cases=cases):
                self.reorder(cases=cases, status=400)
                self.assertEqual(
                    self.ordered(self.plan), [self.case.pk, self.second.pk]
                )

    def test_drag_between_sections_preserves_execution_and_results(self):
        result = record_result(
            self.user,
            self.execution.pk,
            status=self.passed,
            comment="Keep me",
            step_values=self.step_values(),
        )
        snapshot = snapshot_execution(self.execution)
        self.post(
            {
                "action": "order",
                "orders": [
                    self.order(
                        self.plan, [self.case.pk, self.second.pk], [self.second.pk]
                    ),
                    self.order(self.child, [], [self.case.pk]),
                ],
            }
        )
        self.assertEqual(self.ordered(self.plan), [self.second.pk])
        self.assertEqual(self.ordered(self.child), [self.case.pk])
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.case_id, self.case.pk)
        self.assertEqual(self.execution.run_id, self.test_run.pk)
        self.assertTrue(ExecutionResult.objects.filter(pk=result.pk).exists())
        self.assertEqual(snapshot_execution(self.execution).pk, snapshot.pk)

    def test_cross_section_order_requires_removal_permission_before_any_write(self):
        self.reader("testcases.change_testcaseplan", "testcases.add_testcaseplan")
        self.post(
            {
                "action": "order",
                "orders": [
                    self.order(
                        self.plan, [self.case.pk, self.second.pk], [self.second.pk]
                    ),
                    self.order(self.child, [], [self.case.pk]),
                ],
            },
            403,
        )
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])
        self.assertEqual(self.ordered(self.child), [])

    def test_duplicate_in_destination_drag_does_not_lose_source(self):
        self.child.add_case(self.case)
        self.post(
            {
                "action": "order",
                "orders": [
                    self.order(
                        self.plan, [self.case.pk, self.second.pk], [self.second.pk]
                    ),
                    self.order(
                        self.child, [self.case.pk], [self.case.pk, self.case.pk]
                    ),
                ],
            },
            400,
        )
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])
        self.assertEqual(self.ordered(self.child), [self.case.pk])

    def test_bulk_move_appends_and_deduplicates_shared_case(self):
        grandchild = self.section(parent=self.child)
        self.child.add_case(self.case)
        grandchild.add_case(self.second, 40)
        self.transfer(
            items=[
                {"section": self.plan.pk, "case": self.case.pk},
                {"section": self.child.pk, "case": self.case.pk},
            ],
            destination=grandchild,
        )
        self.assertEqual(self.ordered(self.plan), [self.second.pk])
        self.assertEqual(self.ordered(self.child), [])
        self.assertEqual(self.ordered(grandchild), [self.second.pk, self.case.pk])

    def test_bulk_move_to_existing_link_keeps_target_link_and_order(self):
        existing = self.child.add_case(self.case, 75)
        self.transfer()
        existing.refresh_from_db()
        self.assertEqual(existing.sortkey, 75)
        self.assertEqual(self.ordered(self.child), [self.case.pk])
        self.assertEqual(self.ordered(self.plan), [self.second.pk])

    def test_move_within_same_section_keeps_membership(self):
        self.transfer(destination=self.plan)
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])

    def test_missing_last_selection_rolls_back_entire_move(self):
        self.transfer(
            items=[
                {"section": self.plan.pk, "case": self.case.pk},
                {"section": self.plan.pk, "case": 999999},
            ],
            status=409,
        )
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])
        self.assertEqual(self.ordered(self.child), [])

    def test_copy_preserves_definition_and_creates_independent_draft(self):
        shared = SharedStepSet.objects.create(
            product=self.product, name="Reusable", steps=[{"action": "Shared action"}]
        )
        self.workflow.steps.append({"shared_id": shared.pk})
        self.field()
        self.workflow.custom_values = {"risk": "High"}
        self.workflow.save()
        tag = TagFactory()
        component = ComponentFactory(product=self.product)
        self.case.add_tag(tag)
        self.case.add_component(component)
        Property.objects.create(case=self.case, name="browser", value="Firefox")
        result = self.transfer(mode="copy")
        copied = TestCase.objects.get(pk=result["cases"][0])
        self.assertNotEqual(copied.pk, self.case.pk)
        self.assertEqual(copied.summary, self.case.summary)
        self.assertEqual(copied.text, self.case.text)
        self.assertEqual(copied.author_id, self.user.pk)
        self.assertFalse(copied.case_status.is_confirmed)
        workflow = CaseWorkflow.objects.get(case=copied)
        self.assertEqual(workflow.steps, self.workflow.steps)
        self.assertEqual(workflow.custom_values, self.workflow.custom_values)
        self.assertEqual(list(copied.tag.all()), [tag])
        self.assertEqual(list(copied.component.all()), [component])
        self.assertEqual(
            list(Property.objects.filter(case=copied).values_list("name", "value")),
            [("browser", "Firefox")],
        )
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])
        self.assertEqual(self.ordered(self.child), [copied.pk])
        self.assertFalse(copied.executions.exists())
        workflow.steps = [{"action": "Changed copy"}]
        workflow.save()
        self.workflow.refresh_from_db()
        self.assertNotEqual(workflow.steps, self.workflow.steps)

    def test_copy_failure_rolls_back_prior_clones(self):
        before = TestCase.objects.count()
        original = TestCase.clone
        calls = []

        def fail_second(case, *args, **kwargs):
            calls.append(case.pk)
            if len(calls) == 2:
                raise ValidationError("Invalid steps")
            return original(case, *args, **kwargs)

        with patch.object(TestCase, "clone", fail_second):
            self.transfer(
                mode="copy",
                items=[
                    {"section": self.plan.pk, "case": self.case.pk},
                    {"section": self.plan.pk, "case": self.second.pk},
                ],
                status=400,
            )
        self.assertEqual(TestCase.objects.count(), before)
        self.assertEqual(self.ordered(self.child), [])

    def test_copy_requires_add_case_and_link_permissions(self):
        self.reader("testcases.add_testcaseplan")
        self.transfer(mode="copy", status=403)
        self.assertEqual(self.ordered(self.child), [])

    def test_move_checks_every_selected_membership_permission(self):
        user = self.reader("testcases.add_testcaseplan")
        link = TestCasePlan.objects.get(plan=self.plan, case=self.case)
        assign_perm("testcases.delete_testcaseplan", user, link)
        self.transfer(
            items=[
                {"section": self.plan.pk, "case": self.case.pk},
                {"section": self.plan.pk, "case": self.second.pk},
            ],
            status=403,
        )
        self.assertEqual(self.ordered(self.plan), [self.case.pk, self.second.pk])
        self.assertEqual(self.ordered(self.child), [])

    def test_cannot_transfer_to_other_root_or_foreign_product(self):
        outside = TestPlanFactory(product=self.product, product_version=self.version)
        self.transfer(destination=outside, status=400)
        foreign = TestPlanFactory(parent=self.plan)
        self.transfer(destination=foreign, status=400)
        foreign_case = TestCaseFactory(category=CategoryFactory())
        self.plan.add_case(foreign_case)
        self.transfer(
            items=[
                {"section": self.plan.pk, "case": self.case.pk},
                {"section": self.plan.pk, "case": foreign_case.pk},
            ],
            status=400,
        )
        self.assertEqual(self.ordered(self.child), [])
        self.assertTrue(
            TestCasePlan.objects.filter(plan=self.plan, case=self.case).exists()
        )

    def test_anonymous_and_hidden_root_denied(self):
        self.client.logout()
        self.reorder(status=403)
        self.client.force_login(self.restricted_user())
        self.reorder(status=403)

    def test_invalid_request_shapes_and_boolean_ids_rejected(self):
        for data in (
            [],
            None,
            {"action": "unknown"},
            {"action": "create", "section": True, "name": "Name"},
            {"action": "order", "orders": []},
            {
                "action": "transfer",
                "mode": "move",
                "destination": self.child.pk,
                "items": [],
            },
        ):
            with self.subTest(data=data):
                response = self.client.post(
                    self.url, json.dumps(data), content_type="application/json"
                )
                self.assertEqual(response.status_code, 400, response.content)
        response = self.client.post(
            self.url, b"{broken", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_post_and_csrf_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        data = {"action": "rename", "section": self.plan.pk, "name": "CSRF check"}
        self.assertEqual(
            client.post(self.url, data, content_type="application/json").status_code,
            403,
        )
        page = client.get(self.plan.get_absolute_url())
        self.assertEqual(page.status_code, 200)
        response = client.post(
            self.url,
            data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(page, 'id="organization-permissions"')

    def test_readonly_page_hides_mutation_capabilities(self):
        self.reader()
        response = self.client.get(self.plan.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["organization_permissions"][str(self.plan.pk)],
            {
                "create": False,
                "rename": False,
                "reorder": False,
                "move": False,
                "copy": False,
            },
        )

    def test_configuration_run_includes_nested_cases_once_in_section_order(self):
        TestCasePlan.objects.filter(plan=self.plan).delete()
        grandchild = self.section(parent=self.child)
        self.child.add_case(self.case, 20)
        self.child.add_case(self.second, 10)
        self.second.case_status = self.case.case_status
        self.second.save()
        grandchild.add_case(self.case, 10)
        third = TestCaseFactory(
            category=self.case.category, case_status=self.case.case_status
        )
        third.save()  # The factory mutes the history required by execution snapshots.
        grandchild.add_case(third, 20)
        outside = TestPlanFactory(product=self.product, product_version=self.version)
        outside.add_case(
            TestCaseFactory(
                category=self.case.category, case_status=self.case.case_status
            )
        )
        runs = create_configuration_runs(
            self.user, self.cycle, self.plan, self.build, []
        )
        self.assertEqual(
            list(
                runs[0].executions.order_by("sortkey").values_list("case_id", flat=True)
            ),
            [self.second.pk, self.case.pk, third.pk],
        )

    def test_configuration_run_does_not_silently_omit_hidden_subsection(self):
        user = self.restricted_user()
        for permission in (
            "workflow.change_testcycle",
            "testruns.add_testrun",
            "testruns.add_testexecution",
            "management.view_build",
            "testcases.view_testcase",
        ):
            assign_perm(permission, user)
        assign_perm("testplans.view_testplan", user, self.plan)
        self.child.add_case(self.case)
        before = TestRun.objects.count()
        with self.assertRaises(PermissionDenied):
            create_configuration_runs(user, self.cycle, self.plan, self.build, [])
        self.assertEqual(TestRun.objects.count(), before)

    def test_default_new_run_includes_descendant_cases_but_explicit_selection_stays(
        self,
    ):
        self.child.add_case(self.case)
        third = TestCaseFactory(
            category=self.case.category, case_status=self.case.case_status
        )
        self.child.add_case(third)
        url = reverse("testruns-from-plan", args=[self.plan.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.context["test_cases"].values_list("pk", flat=True)),
            {self.case.pk, third.pk},
        )
        response = self.client.get(url, {"c": third.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["test_cases"].values_list("pk", flat=True)),
            [third.pk],
        )

    def test_default_new_run_rejects_legacy_foreign_product_section_cleanly(self):
        TestPlanFactory(parent=self.plan)
        response = self.client.get(reverse("testruns-from-plan", args=[self.plan.pk]))
        self.assertEqual(response.status_code, 400)
