from http import HTTPStatus

from django.test import override_settings
from django.urls import reverse
from parameterized import parameterized

from tcms.testcases.models import BugSystem, TestCaseFieldSettings
from tcms.tests import LoggedInTestCase
from tcms.tests.factories import TestCaseFactory
from tcms.utils.permissions import initiate_user_with_default_setups


class TestTestCaseAdmin(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        initiate_user_with_default_setups(cls.tester)
        cls.test_case = TestCaseFactory()

    def test_add_view_always_redirects_to_new_case_view(self):
        response = self.client.get(reverse("admin:testcases_testcase_add"))
        self.assertRedirects(response, reverse("testcases-new"))

    def test_change_view_redirects_to_testcase_get_view(self):
        response = self.client.get(
            reverse("admin:testcases_testcase_change", args=[self.test_case.pk])
        )
        self.assertRedirects(
            response, reverse("testcases-get", args=[self.test_case.pk])
        )


@override_settings(LANGUAGE_CODE="en")
class TestBugSystemAdmin(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        initiate_user_with_default_setups(cls.tester)
        cls.bug_system = BugSystem.objects.create(
            name="Original Bugzilla",
            tracker_type="tcms.issuetracker.types.Bugzilla",
            base_url="https://bugzilla.example.com",
            api_password="hello-world",  # nosec:B106:hardcoded_password_funcarg
        )

    def test_change_view_saves_updated_record(self):
        response = self.client.post(
            reverse("admin:testcases_bugsystem_change", args=[self.bug_system.pk]),
            {
                "name": "Renamed Bugzilla",
                "tracker_type": self.bug_system.tracker_type,
                "base_url": "https://bugzilla.example.org",
            },
            follow=True,
        )

        self.assertEqual(HTTPStatus.OK, response.status_code)

        self.bug_system.refresh_from_db()
        self.assertEqual("Renamed Bugzilla", self.bug_system.name)
        self.assertEqual("https://bugzilla.example.org", self.bug_system.base_url)
        # will always overwrite this field
        self.assertEqual("", self.bug_system.api_password)

    @parameterized.expand(
        [
            ("base_class", "tcms.issuetracker.base.IssueTrackerType"),
            ("raises_in_init", "tcms.issuetracker.tests.raise.Bogus"),
            ("random_dotted_path", "random.dotted.string"),
            ("not_a_dotted_path", "random string"),
        ]
    )
    def test_add_view_with_invalid_tracker_type_will_fail(self, _name, tracker_type):
        response = self.client.post(
            reverse("admin:testcases_bugsystem_add"),
            {
                "name": f"Bogus tracker: {_name}",
                "tracker_type": tracker_type,
                "base_url": "https://bogus.example.com",
            },
            follow=True,
        )

        self.assertContains(response, "Please correct the error below.")
        self.assertContains(
            response,
            f"Select a valid choice. {tracker_type} is not one of the available choices.",
        )
        self.assertFalse(
            BugSystem.objects.filter(name=f"Bogus tracker: {_name}").exists()
        )

    @parameterized.expand(
        [
            ("base_class", "tcms.issuetracker.base.IssueTrackerType"),
            ("raises_in_init", "tcms.issuetracker.tests.raise.Bogus"),
            ("random_dotted_path", "random.dotted.string"),
            ("not_a_dotted_path", "random string"),
        ]
    )
    def test_change_view_with_invalid_tracker_type_will_fail(self, _name, tracker_type):
        response = self.client.post(
            reverse("admin:testcases_bugsystem_change", args=[self.bug_system.pk]),
            {
                "name": self.bug_system.name,
                "tracker_type": tracker_type,
                "base_url": self.bug_system.base_url,
            },
            follow=True,
        )

        self.assertContains(response, "Please correct the error below.")
        self.assertContains(
            response,
            f"Select a valid choice. {tracker_type} is not one of the available choices.",
        )

        self.bug_system.refresh_from_db()
        self.assertEqual(
            "tcms.issuetracker.types.Bugzilla", self.bug_system.tracker_type
        )


class TestTestCaseFieldSettingsAdmin(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        initiate_user_with_default_setups(cls.tester)

    def test_changelist_redirects_to_change_view(self):
        settings_obj = TestCaseFieldSettings.get_settings()
        response = self.client.get(
            reverse("admin:testcases_testcasefieldsettings_changelist")
        )
        self.assertRedirects(
            response,
            reverse(
                "admin:testcases_testcasefieldsettings_change",
                args=[settings_obj.pk],
            ),
        )

    def test_change_view_saves_updated_settings(self):
        settings_obj = TestCaseFieldSettings.get_settings()
        response = self.client.post(
            reverse(
                "admin:testcases_testcasefieldsettings_change",
                args=[settings_obj.pk],
            ),
            {
                "plan_show_status": "on",
                "plan_show_automated": "on",
                "plan_show_priority": "on",
                "plan_show_category": "on",
                "plan_show_product": "on",
                # plan_show_author omitted -> turns False
                "plan_show_default_tester": "on",
                "plan_show_reviewer": "on",
                "run_show_status": "on",
                "run_show_automated": "on",
                "run_show_priority": "on",
                "run_show_category": "on",
                "run_show_product": "on",
                "run_show_author": "on",
                "run_show_default_tester": "on",
                "run_show_assignee": "on",
                "run_show_tested_by": "on",
                "run_show_bugs": "on",
                "run_show_tags": "on",
                "run_show_components": "on",
            },
            follow=True,
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        settings_obj.refresh_from_db()
        self.assertFalse(settings_obj.plan_show_author)
        self.assertTrue(settings_obj.plan_show_product)
        self.assertTrue(settings_obj.run_show_author)
        self.assertTrue(settings_obj.run_show_product)
