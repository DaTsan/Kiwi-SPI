from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from guardian.shortcuts import assign_perm

from tcms.testcases.models import TestCaseStatus
from tcms.testruns.models import Environment, EnvironmentProperty, TestRun
from tcms.tests.factories import (
    BuildFactory,
    ProductFactory,
    TestCaseFactory,
    TestPlanFactory,
)
from tcms.workflow.forms import CustomValuesForm, StepFormSet
from tcms.workflow.models import (
    CaseWorkflow,
    CycleRun,
    ExecutionResult,
    Milestone,
    RunMilestone,
    SharedStepSet,
    TestCycle,
)
from tcms.workflow.services import (
    assign_run,
    create_configuration_runs,
    link_run,
    record_result,
    resolve_steps,
    snapshot_execution,
    validate_custom_values,
)
from tcms.workflow.validators import validate_choices, validate_steps

from .base import WorkflowTestCase


class DefinitionTests(WorkflowTestCase):
    def test_milestone_dates_and_hierarchy(self):
        child = Milestone.objects.create(
            product=self.product, name="Child", parent=self.milestone
        )
        self.milestone.parent = child
        with self.assertRaises(ValidationError):
            self.milestone.full_clean()
        self.milestone.parent = None
        self.milestone.start_date, self.milestone.due_date = date(2026, 2, 2), date(
            2026, 1, 1
        )
        with self.assertRaises(ValidationError):
            self.milestone.full_clean()

    def test_milestone_cross_product_parent(self):
        other = Milestone(product=ProductFactory(), name="Other", parent=self.milestone)
        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_milestone_product_cannot_change(self):
        self.milestone.product = ProductFactory()
        with self.assertRaises(ValidationError):
            self.milestone.full_clean()

    def test_cycle_cross_product_and_frozen_milestone(self):
        self.cycle.product = ProductFactory()
        with self.assertRaises(ValidationError):
            self.cycle.full_clean()
        self.cycle.refresh_from_db()
        link_run(self.user, self.cycle, self.test_run)
        self.cycle.milestone = None
        with self.assertRaises(ValidationError):
            self.cycle.full_clean()

    def test_step_validation_rejects_bad_shapes(self):
        for value in (
            {},
            ["text"],
            [{"action": " "}],
            [{"shared_id": True}],
            [{"shared_id": 1, "action": "x"}],
            [{"action": "x", "unexpected": "y"}],
            [{"action": "x"}] * 201,
        ):
            with self.subTest(value=str(value)[:80]), self.assertRaises(
                ValidationError
            ):
                validate_steps(value)

    def test_shared_set_does_not_allow_nested_references(self):
        shared = SharedStepSet(
            product=self.product, name="Recursive", steps=[{"shared_id": 1}]
        )
        with self.assertRaises(ValidationError):
            shared.full_clean()

    def test_shared_reference_rejects_other_product(self):
        shared = SharedStepSet.objects.create(
            product=ProductFactory(), name="Other", steps=[{"action": "Private"}]
        )
        with self.assertRaises(ValidationError):
            resolve_steps([{"shared_id": shared.pk}], self.product.pk)

    def test_shared_changes_propagate_but_snapshot_stays_frozen(self):
        shared = SharedStepSet.objects.create(
            product=self.product, name="Login", steps=[{"action": "Old login"}]
        )
        self.workflow.steps = [{"shared_id": shared.pk}]
        self.workflow.save()
        execution = self.test_run.create_execution(self.case, assignee=self.user)[0]
        shared.steps = [{"action": "New login"}]
        shared.save()
        self.assertEqual(
            resolve_steps(self.workflow.steps, self.product.pk)[0]["action"],
            "New login",
        )
        self.assertEqual(snapshot_execution(execution).steps[0]["action"], "Old login")

    def test_snapshot_is_immutable_and_does_not_follow_case_edits(self):
        snapshot = snapshot_execution(self.execution)
        self.case.summary = "Changed"
        self.case.save()
        self.assertNotEqual(snapshot_execution(self.execution).case_summary, "Changed")
        with self.assertRaises(ValidationError):
            snapshot.save()

    def test_step_reorder_and_delete(self):
        data = self.step_post(
            [
                {"action": "First", "ORDER": 3},
                {"action": "Second", "ORDER": 1},
                {"action": "Removed", "DELETE": "on", "ORDER": 2},
            ]
        )
        form = StepFormSet(
            data,
            prefix="steps",
            form_kwargs={"product_id": self.product.pk, "user": self.user},
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            [step["action"] for step in form.as_steps()], ["Second", "First"]
        )

    def test_choice_validation(self):
        for choices in (["Same", "Same"], [""], [{}]):
            with self.subTest(choices=choices), self.assertRaises(ValidationError):
                validate_choices(choices)

    def test_custom_definition_type_is_immutable(self):
        field = self.field()
        field.kind = "integer"
        with self.assertRaises(ValidationError):
            field.full_clean()

    def test_custom_values_all_types_and_required_false_zero(self):
        self.field("count", "integer", required=True)
        self.field("enabled", "checkbox", required=True)
        self.field("risk", "select", choices=["High", "Low"])
        self.field("day", "date")
        self.field("link", "url")
        values = {
            "count": 0,
            "enabled": False,
            "risk": "High",
            "day": "2026-10-11",
            "link": "https://example.com/test",
        }
        self.assertEqual(
            validate_custom_values(self.product.pk, "case", values), values
        )
        form = CustomValuesForm(
            {
                f"custom_{key}": value
                for key, value in values.items()
                if key != "enabled"
            },
            product_id=self.product.pk,
            entity="case",
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.values()["enabled"])

    def test_custom_values_reject_wrong_types_and_unknown_keys(self):
        for key, kind, invalid in (
            ("count", "integer", True),
            ("day", "date", "2026-02-30"),
            ("link", "url", "javascript:alert(1)"),
            ("enabled", "checkbox", "yes"),
            ("risk", "select", "Unknown"),
        ):
            self.field(key, kind, choices=["Known"] if kind == "select" else [])
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                validate_custom_values(self.product.pk, "case", {key: invalid})
        with self.assertRaises(ValidationError):
            validate_custom_values(self.product.pk, "case", {"foreign": "secret"})

    def test_required_field_can_be_deactivated(self):
        field = self.field(required=True)
        with self.assertRaises(ValidationError):
            validate_custom_values(self.product.pk, "case", {})
        field.is_active = False
        field.save()
        validate_custom_values(self.product.pk, "case", {})

    def test_clone_retains_steps_shared_references_and_fields(self):
        self.field()
        shared = SharedStepSet.objects.create(
            product=self.product, name="Shared", steps=[{"action": "Shared action"}]
        )
        self.workflow.steps = [{"shared_id": shared.pk}]
        self.workflow.custom_values = {"risk": "High"}
        self.workflow.save()
        clone = self.case.clone(self.user, [self.plan])
        self.assertEqual(clone.workflow.steps, self.workflow.steps)
        self.assertEqual(clone.workflow.custom_values, {"risk": "High"})

    def test_clone_to_another_product_flattens_shared_steps(self):
        self.field()
        shared = SharedStepSet.objects.create(
            product=self.product, name="Shared", steps=[{"action": "Shared action"}]
        )
        self.workflow.steps = [{"shared_id": shared.pk}]
        self.workflow.custom_values = {"risk": "High"}
        self.workflow.save()
        other_plan = TestPlanFactory()
        clone = self.case.clone(self.user, [other_plan])
        self.assertEqual(clone.workflow.steps[0]["action"], "Shared action")
        self.assertNotIn("shared_id", clone.workflow.steps[0])
        self.assertEqual(clone.workflow.custom_values, {})


class PlanningTests(WorkflowTestCase):
    def test_creates_separate_runs_with_properties_snapshots_and_links(self):
        environments = [
            Environment.objects.create(name=name) for name in ("Chrome", "Firefox")
        ]
        for environment in environments:
            EnvironmentProperty.objects.create(
                environment=environment, name="browser", value=environment.name
            )
        unconfirmed = TestCaseFactory(
            category=self.case.category,
            case_status=TestCaseStatus.objects.filter(is_confirmed=False).first(),
        )
        self.plan.add_case(unconfirmed, 20)
        runs = create_configuration_runs(
            self.user, self.cycle, self.plan, self.build, environments
        )
        self.assertEqual(len(runs), 2)
        for run, environment in zip(runs, environments):
            self.assertEqual(run.executions.count(), 1)
            self.assertEqual(
                run.property_set.get(name="browser").value, environment.name
            )
            self.assertEqual(run.cycle_link.cycle, self.cycle)
            self.assertEqual(run.milestone_link.milestone, self.milestone)
            self.assertEqual(
                run.executions.first().workflow_snapshot.steps, self.workflow.steps
            )

    def test_default_configuration_creates_single_run(self):
        self.assertEqual(
            len(
                create_configuration_runs(
                    self.user, self.cycle, self.plan, self.build, []
                )
            ),
            1,
        )

    def test_wrong_build_does_not_create_partial_runs(self):
        before = TestRun.objects.count()
        with self.assertRaises(ValidationError):
            create_configuration_runs(
                self.user, self.cycle, self.plan, BuildFactory(), []
            )
        self.assertEqual(TestRun.objects.count(), before)

    def test_empty_plan_rejected(self):
        plan = TestPlanFactory(product=self.product, product_version=self.version)
        with self.assertRaises(ValidationError):
            create_configuration_runs(self.user, self.cycle, plan, self.build, [])

    def test_completed_cycle_rejected(self):
        self.cycle.is_completed = True
        self.cycle.save()
        with self.assertRaises(ValidationError):
            create_configuration_runs(self.user, self.cycle, self.plan, self.build, [])

    def test_link_cannot_move_run_to_different_cycle(self):
        link_run(self.user, self.cycle, self.test_run)
        other = TestCycle.objects.create(product=self.product, name="Other")
        with self.assertRaises(ValidationError):
            link_run(self.user, other, self.test_run)
        self.assertEqual(self.test_run.cycle_link.cycle, self.cycle)

    def test_assignment_checks_product_and_cycle_milestone(self):
        with self.assertRaises(ValidationError):
            assign_run(self.user, self.test_run, cycle=self.cycle)
        assign_run(self.user, self.test_run, milestone=self.milestone, cycle=self.cycle)
        other = Milestone.objects.create(product=ProductFactory(), name="Other")
        with self.assertRaises(ValidationError):
            assign_run(self.user, self.test_run, milestone=other)
        self.assertEqual(CycleRun.objects.get(run=self.test_run).cycle, self.cycle)
        self.assertEqual(
            RunMilestone.objects.get(run=self.test_run).milestone, self.milestone
        )

    def test_unauthorized_configuration_creation(self):
        with self.assertRaises(PermissionDenied):
            create_configuration_runs(
                self.restricted_user(), self.cycle, self.plan, self.build, []
            )


class ResultTests(WorkflowTestCase):
    def test_multiple_attempts_preserve_history_and_update_core_execution(self):
        first = record_result(
            self.user,
            self.execution.pk,
            status=self.failed,
            comment="Failure",
            defects="BUG-1",
            elapsed_seconds=30,
            step_values=self.step_values(self.failed),
        )
        second = record_result(
            self.user,
            self.execution.pk,
            status=self.passed,
            comment="Fixed",
            elapsed_seconds=0,
            step_values=self.step_values(),
        )
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, self.passed)
        self.assertEqual(self.execution.tested_by, self.user)
        self.assertIsNotNone(self.execution.stop_date)
        self.assertEqual(
            list(self.execution.results.values_list("pk", flat=True)),
            [second.pk, first.pk],
        )
        first.refresh_from_db()
        self.assertEqual(first.comment, "Failure")
        self.assertEqual(first.defects, "BUG-1")
        with self.assertRaises(ValidationError):
            first.save()

    def test_pending_result_reopens_execution_timing(self):
        record_result(
            self.user,
            self.execution.pk,
            status=self.idle,
            step_values=self.step_values(self.idle),
        )
        self.execution.refresh_from_db()
        self.assertIsNone(self.execution.stop_date)

    def test_incomplete_steps_reject_result_atomically(self):
        for values in (
            [],
            [{"status": self.failed.pk}],
            [{"status": -1}],
            [{"status": True}],
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                record_result(
                    self.user, self.execution.pk, status=self.passed, step_values=values
                )
        self.assertEqual(ExecutionResult.objects.count(), 0)

    def test_invalid_time_rejected(self):
        for seconds in (-1, True, 604801, "30"):
            with self.subTest(seconds=seconds), self.assertRaises(ValidationError):
                record_result(
                    self.user,
                    self.execution.pk,
                    status=self.passed,
                    elapsed_seconds=seconds,
                    step_values=self.step_values(),
                )

    def test_closed_run_rejects_new_results(self):
        self.test_run.stop_date = timezone.now()
        self.test_run.save()
        with self.assertRaises(ValidationError):
            record_result(
                self.user,
                self.execution.pk,
                status=self.passed,
                step_values=self.step_values(),
            )

    def test_result_fields_validate_and_freeze_labels(self):
        field = self.field("build_url", "url", entity="result", required=True)
        with self.assertRaises(ValidationError):
            record_result(
                self.user,
                self.execution.pk,
                status=self.passed,
                step_values=self.step_values(),
            )
        result = record_result(
            self.user,
            self.execution.pk,
            status=self.passed,
            step_values=self.step_values(),
            custom_values={"build_url": "https://example.com/42"},
        )
        field.label = "New label"
        field.save()
        result.refresh_from_db()
        self.assertEqual(result.custom_values["build_url"]["label"], "Build_Url")

    def test_object_permissions_allow_only_authorized_execution(self):
        user = self.restricted_user()
        for permission, obj in (
            ("testruns.view_testrun", self.test_run),
            ("testruns.view_testexecution", self.execution),
            ("testruns.change_testexecution", self.execution),
        ):
            assign_perm(permission, user, obj)
        assign_perm("workflow.add_executionresult", user)
        result = record_result(
            user, self.execution.pk, status=self.passed, step_values=self.step_values()
        )
        self.assertEqual(result.author, user)

    def test_execution_permission_does_not_bypass_hidden_run(self):
        user = self.restricted_user()
        assign_perm("testruns.change_testexecution", user, self.execution)
        assign_perm("testruns.view_testexecution", user, self.execution)
        assign_perm("workflow.add_executionresult", user)
        with self.assertRaises(PermissionDenied):
            record_result(
                user,
                self.execution.pk,
                status=self.passed,
                step_values=self.step_values(),
            )
