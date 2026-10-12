from django.test import TestCase

from tcms.testcases.models import TestCaseStatus
from tcms.testruns.models import TestExecutionStatus
from tcms.tests.factories import (
    BuildFactory,
    CategoryFactory,
    ProductFactory,
    TestCaseFactory,
    TestPlanFactory,
    TestRunFactory,
    UserFactory,
    VersionFactory,
)
from tcms.workflow.models import CaseWorkflow, CustomField, Milestone, TestCycle


class WorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory(is_superuser=True)
        cls.product = ProductFactory()
        cls.version = VersionFactory(product=cls.product)
        cls.build = BuildFactory(version=cls.version)
        cls.plan = TestPlanFactory(
            product=cls.product, product_version=cls.version, author=cls.user
        )
        cls.case = TestCaseFactory(
            category=CategoryFactory(product=cls.product),
            author=cls.user,
            case_status=TestCaseStatus.objects.filter(is_confirmed=True).first(),
        )
        cls.case.save()  # The upstream factory mutes post_save history signals.
        cls.plan.add_case(cls.case, 10)
        cls.workflow = CaseWorkflow.objects.create(
            case=cls.case,
            steps=[
                {
                    "action": "Open login",
                    "expected": "Login is visible",
                    "reference": "REQ-1",
                }
            ],
        )
        cls.milestone = Milestone.objects.create(product=cls.product, name="Release 1")
        cls.cycle = TestCycle.objects.create(
            product=cls.product, milestone=cls.milestone, name="Regression"
        )
        cls.test_run = TestRunFactory(
            plan=cls.plan, build=cls.build, manager=cls.user, default_tester=cls.user
        )
        cls.execution = cls.test_run.create_execution(cls.case, assignee=cls.user)[0]
        cls.passed = TestExecutionStatus.objects.filter(weight__gt=0).last()
        cls.failed = TestExecutionStatus.objects.filter(weight__lt=0).first()
        cls.idle = TestExecutionStatus.objects.filter(weight=0).first()

    def field(self, key="risk", kind="text", entity="case", **kwargs):
        return CustomField.objects.create(
            product=self.product,
            key=key,
            label=key.title(),
            kind=kind,
            entity=entity,
            **kwargs,
        )

    def step_values(self, status=None):
        return [{"status": (status or self.passed).pk, "actual": "Observed result"}]

    def restricted_user(self):
        user = UserFactory()
        user.groups.clear()
        user.user_permissions.clear()
        return user

    @staticmethod
    def step_post(steps, prefix="steps"):
        data = {
            f"{prefix}-TOTAL_FORMS": str(len(steps)),
            f"{prefix}-INITIAL_FORMS": "0",
        }
        for index, step in enumerate(steps):
            data.update(
                {f"{prefix}-{index}-{key}": value for key, value in step.items()}
            )
        return data
