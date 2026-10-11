"""Subsection ordering preserves the tree, memberships and test results."""

from importlib import import_module
from operator import attrgetter, itemgetter
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.urls import reverse
from guardian.shortcuts import assign_perm

from tcms.rpc.api.testplan import tree
from tcms.testcases.models import TestCasePlan
from tcms.testplans.models import TestPlan
from tcms.testplans.organization import confirmed_tree_cases
from tcms.tests.factories import TestCaseFactory, TestPlanFactory
from tcms.workflow.services import create_configuration_runs, record_result
from tcms.workflow.tests.base import WorkflowTestCase


class SectionOrderTests(WorkflowTestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("plan-case-organization", args=[self.plan.pk])
        self.first = self.section(self.plan, "First")
        self.grandchild = self.section(self.first, "Grandchild")
        self.second = self.section(self.plan, "Second")
        self.second.add_case(self.case)

    def section(self, parent, name="Subsection"):
        return TestPlanFactory(
            name=name,
            parent=parent,
            product=self.product,
            product_version=self.version,
            type=self.plan.type,
        )

    def post(self, *, parent=None, previous=None, sections=None, status=200):
        response = self.client.post(
            self.url,
            {
                "action": "section_order",
                "parent": parent.pk if parent else self.plan.pk,
                "previous": (
                    previous
                    if previous is not None
                    else [self.first.pk, self.second.pk]
                ),
                "sections": (
                    sections
                    if sections is not None
                    else [self.second.pk, self.first.pk]
                ),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def ordered(self):
        return list(self.plan.children.values_list("pk", flat=True))

    def test_order_is_durable_and_used_by_rpc_and_family_tree(self):
        expected = [self.plan.pk, self.second.pk, self.first.pk, self.grandchild.pk]
        self.assertEqual(
            self.post(), {"parent": self.plan.pk, "sections": expected[1:3]}
        )
        self.assertEqual(self.ordered(), expected[1:3])
        self.assertEqual(
            list(map(itemgetter("id"), tree(self.plan.pk, True))), expected
        )
        self.assertEqual(
            list(self.first.tree_as_list().values_list("pk", flat=True)), expected
        )
        page = self.client.get(self.plan.get_absolute_url())
        self.assertEqual(page.status_code, 200)
        family = self.plan.tree_view_html()
        self.assertLess(family.index("Second"), family.index("First"))
        self.assertLess(family.index("First"), family.index("Grandchild"))
        self.second.refresh_from_db()
        self.assertEqual(self.second.position, 10)
        history = self.second.history.first()
        self.assertEqual(history.position, 10)
        self.assertEqual(history.history_user_id, self.user.pk)
        self.assertIn("position", history.history_change_reason)

    def test_nested_siblings_can_be_reordered_independently(self):
        another = self.section(self.first)
        self.post(
            parent=self.first,
            previous=[self.grandchild.pk, another.pk],
            sections=[another.pk, self.grandchild.pk],
        )
        self.assertEqual(self.ordered(), [self.first.pk, self.second.pk])
        self.assertEqual(
            list(self.first.children.values_list("pk", flat=True)),
            [another.pk, self.grandchild.pk],
        )

    def test_contents_memberships_and_results_remain_unchanged(self):
        self.grandchild.add_case(self.case, 17)
        record_result(
            self.user,
            self.execution.pk,
            status=self.passed,
            step_values=self.step_values(),
        )
        before_plans = list(
            TestPlan.objects.order_by("pk").values(
                "pk", "parent_id", "name", "text", "author_id"
            )
        )
        before_links = list(TestCasePlan.objects.order_by("pk").values())
        before_execution = self.execution.__class__.objects.values().get(
            pk=self.execution.pk
        )
        before_results = list(self.execution.results.values())
        self.post()
        self.assertEqual(
            list(
                TestPlan.objects.order_by("pk").values(
                    "pk", "parent_id", "name", "text", "author_id"
                )
            ),
            before_plans,
        )
        self.assertEqual(
            list(TestCasePlan.objects.order_by("pk").values()), before_links
        )
        self.assertEqual(
            self.execution.__class__.objects.values().get(pk=self.execution.pk),
            before_execution,
        )
        self.assertEqual(list(self.execution.results.values()), before_results)

    def test_new_subsection_and_clone_append_after_reordering(self):
        self.post()
        added = self.section(self.plan)
        cloned = self.plan.clone(set_parent=True)
        self.assertEqual(
            self.ordered(), [self.second.pk, self.first.pk, added.pk, cloned.pk]
        )
        response = self.client.post(
            self.url,
            {"action": "create", "section": self.plan.pk, "name": "New"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ordered()[-1], response.json()["section"])

    def test_stale_reorder_and_concurrent_creation_return_conflict(self):
        self.post()
        self.post(status=409)
        self.assertEqual(self.ordered(), [self.second.pk, self.first.pk])
        added = self.section(self.plan)
        self.post(
            previous=[self.second.pk, self.first.pk],
            sections=[self.first.pk, self.second.pk],
            status=409,
        )
        self.assertEqual(self.ordered(), [self.second.pk, self.first.pk, added.pk])

    def test_cannot_remove_duplicate_add_or_reparent_sections(self):
        outside = self.section(self.grandchild)
        for sections in (
            [self.first.pk],
            [],
            [self.first.pk, self.first.pk],
            [self.first.pk, self.second.pk, outside.pk],
            [self.first.pk, self.grandchild.pk],
            [self.plan.pk, self.second.pk],
        ):
            with self.subTest(sections=sections):
                self.post(sections=sections, status=400)
                self.assertEqual(self.ordered(), [self.first.pk, self.second.pk])
        self.grandchild.refresh_from_db()
        self.assertEqual(self.grandchild.parent_id, self.first.pk)

    def test_invalid_input_is_rejected(self):
        for values in (
            None,
            {},
            "1,2",
            [True],
            ["1"],
            [0],
            [-1],
            [self.first.pk] * 10001,
        ):
            with self.subTest(value_type=type(values).__name__):
                response = self.client.post(
                    self.url,
                    {
                        "action": "section_order",
                        "parent": self.plan.pk,
                        "previous": values,
                        "sections": [self.second.pk, self.first.pk],
                    },
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.ordered(), [self.first.pk, self.second.pk])

    def test_outside_parent_and_foreign_product_are_rejected(self):
        outside = TestPlanFactory(product=self.product, product_version=self.version)
        self.post(parent=outside, status=400)
        foreign = TestPlanFactory(parent=self.plan)
        self.post(
            previous=[self.first.pk, self.second.pk, foreign.pk],
            sections=[foreign.pk, self.second.pk, self.first.pk],
            status=400,
        )
        self.assertEqual(self.ordered(), [self.first.pk, self.second.pk, foreign.pk])

    def test_readonly_and_case_reorder_permission_do_not_allow_section_changes(self):
        user = self.restricted_user()
        for permission in ("testplans.view_testplan", "testcases.change_testcaseplan"):
            assign_perm(permission, user)
        self.client.force_login(user)
        self.post(status=403)
        self.assertEqual(self.ordered(), [self.first.pk, self.second.pk])

    def test_object_permissions_require_parent_and_every_sibling(self):
        user = self.restricted_user()
        for section in (self.plan, self.first, self.second):
            assign_perm("testplans.view_testplan", user, section)
        assign_perm("testplans.change_testplan", user, self.first)
        assign_perm("testplans.change_testplan", user, self.second)
        self.client.force_login(user)
        self.post(status=403)
        assign_perm("testplans.change_testplan", user, self.plan)
        self.post()
        self.assertEqual(self.ordered(), [self.second.pk, self.first.pk])

    def test_missing_sibling_permission_rolls_back_all_changes(self):
        user = self.restricted_user()
        assign_perm("testplans.view_testplan", user)
        for section in (self.plan, self.second):
            assign_perm("testplans.change_testplan", user, section)
        self.client.force_login(user)
        before = list(TestPlan.objects.order_by("pk").values_list("pk", "position"))
        history_count = TestPlan.history.count()  # pylint: disable=no-member
        self.post(status=403)
        self.assertEqual(
            list(TestPlan.objects.order_by("pk").values_list("pk", "position")), before
        )
        # The history manager is generated at runtime.
        # pylint: disable=no-member
        self.assertEqual(TestPlan.history.count(), history_count)
        # pylint: enable=no-member

    def test_hidden_sibling_is_not_silently_discarded(self):
        user = self.restricted_user()
        assign_perm("testplans.change_testplan", user)
        for section in (self.plan, self.first):
            assign_perm("testplans.view_testplan", user, section)
        self.client.force_login(user)
        self.post(previous=[self.first.pk], sections=[self.first.pk], status=403)

    def test_new_run_uses_reordered_section_tree(self):
        TestCasePlan.objects.filter(plan=self.plan).delete()
        other = TestCaseFactory(
            category=self.case.category, case_status=self.case.case_status
        )
        other.save()
        self.first.add_case(other)
        self.grandchild.add_case(self.case)
        self.post()
        self.assertEqual(
            list(map(attrgetter("pk"), confirmed_tree_cases(self.user, self.plan))),
            [self.case.pk, other.pk],
        )
        runs = create_configuration_runs(
            self.user, self.cycle, self.plan, self.build, []
        )
        self.assertEqual(
            list(
                runs[0].executions.order_by("sortkey").values_list("case_id", flat=True)
            ),
            [self.case.pk, other.pk],
        )

    def test_migration_preserves_previous_primary_key_order(self):
        # Reproduce pre-migration rows without generating new history.
        TestPlan.objects.update(position=0)  # pylint: disable=objects-update-used
        migration = import_module("tcms.testplans.migrations.0014_section_order")
        migration.preserve_sibling_order(apps, SimpleNamespace(connection=connection))
        self.assertEqual(self.ordered(), [self.first.pk, self.second.pk])
        self.assertEqual(
            list(map(itemgetter("id"), tree(self.plan.pk, True))),
            [self.plan.pk, self.first.pk, self.grandchild.pk, self.second.pk],
        )
