# pylint: disable=no-self-use

import traceback

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.forms.widgets import Select
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from tcms.core.admin import ObjectPermissionsAdminMixin
from tcms.core.history import ReadOnlyHistoryAdmin
from tcms.core.widgets import SimpleMDE
from tcms.testcases.models import (
    BugSystem,
    Category,
    Template,
    TestCase,
    TestCaseFieldSettings,
    TestCaseStatus,
)


class TestCaseStatusAdmin(admin.ModelAdmin):
    _for_more_info = _("""For more information about customizing test case statuses see
        <a href="https://kiwitcms.readthedocs.io/en/latest/admin.html#test-case-statuses">
        the documentation</a>!""")
    list_display = ("id", "name", "is_confirmed")
    ordering = ["-is_confirmed", "id"]
    fieldsets = [
        (
            "",
            {
                "fields": ("name", "description", "is_confirmed"),
                "description": f"<h1>{_for_more_info}</h1>",
            },
        ),
    ]

    @admin.options.csrf_protect_m
    def delete_view(self, request, object_id, extra_context=None):
        obj = self.model.objects.get(pk=object_id)

        if (
            not self.model.objects.filter(is_confirmed=obj.is_confirmed)
            .exclude(pk=object_id)
            .exists()
        ):
            messages.add_message(
                request,
                messages.ERROR,
                _("1 confirmed & 1 uncomfirmed status required!"),
            )

            return HttpResponseRedirect(
                reverse("admin:testcases_testcasestatus_changelist")
            )

        return super().delete_view(request, object_id, extra_context)


class TestCaseAdmin(ObjectPermissionsAdminMixin, ReadOnlyHistoryAdmin):
    def add_view(self, request, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("testcases-new"))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("testcases-get", args=[object_id]))


class CategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "product", "description")
    list_filter = ("product",)


class IssueTrackerTypeSelectWidget(Select):
    """
    A select widget which displays the names of all classes
    derived from IssueTrackerType. Skip IssueTrackerType
    because it is doesn't provide implementations for most of its methods.
    """

    _choices = None

    @property
    def choices(self):
        if self._choices is None:
            self._choices = self._types_as_choices()
        return self._choices

    @choices.setter
    def choices(self, _):
        # ChoiceField.__init__ sets ``self.choices = choices``
        # which would override ours.
        pass

    @staticmethod
    def _types_as_choices():
        return (("", ""),) + tuple(
            zip(settings.EXTERNAL_BUG_TRACKERS, settings.EXTERNAL_BUG_TRACKERS)
        )


class IssueTrackerTypeField(forms.ChoiceField):
    """Special choice field which uses the widget above"""

    widget = IssueTrackerTypeSelectWidget

    def valid_value(self, value):
        return value in settings.EXTERNAL_BUG_TRACKERS


class BugSystemAdminForm(forms.ModelForm):
    # make password show asterisks
    api_password = forms.CharField(  # pylint:disable=form-field-help-text-used
        widget=forms.PasswordInput(render_value=False, attrs={"class": "vTextField"}),
        required=False,
        help_text="WARNING: will overwrite existing value",
    )

    # select only tracker types for which we have available integrations
    tracker_type = IssueTrackerTypeField(  # pylint:disable=form-field-help-text-used
        help_text="This determines how Kiwi TCMS integrates with the IT system",
    )

    hc_bug_url = forms.CharField(  # pylint: disable=form-field-label-used
        required=False,
        max_length=1024,
        label=_("Bug URL"),
        widget=admin.widgets.AdminTextInputWidget,
    )

    class Meta:
        model = BugSystem
        fields = "__all__"


class BugSystemAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "base_url")
    fieldsets = [
        (
            "",
            {
                "fields": ("name",),
            },
        ),
        (
            _("External Issue Tracker Integration"),
            {
                "fields": (
                    "tracker_type",
                    "base_url",
                    "api_url",
                    "api_username",
                    "api_password",
                ),
                "description": _("""<h1>Warning: read the
<a href="http://kiwitcms.readthedocs.io/en/latest/admin.html#configure-external-bug-trackers">
Configure external bug trackers</a> section before editting the values below!</h1>"""),
            },
        ),
        (
            _("Configuration health check"),
            {
                "fields": ("hc_bug_url",),
                "description": _(
                    "Kiwi TCMS will try fetching details for the given bug URL using the "
                    "integration defined above! Click the `Save and continue` button and "
                    "watch out for messages at the top of the screen. <strong>WARNING:</strong> "
                    "in case of failures some issue trackers will fall back to fetching details "
                    "via the OpenGraph protocol. In that case the result will include field named "
                    "`from_open_graph`."
                ),
            },
        ),
    ]
    form = BugSystemAdminForm

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # try health check
        bug_url = form.cleaned_data["hc_bug_url"]
        if bug_url:
            try:
                tracker = import_string(obj.tracker_type)(obj, request)
                if not tracker:
                    raise RuntimeError(_("Failed creating Issue Tracker"))

                details = tracker.details(bug_url)

                if details.get("from_open_graph", False):
                    messages.add_message(
                        request,
                        messages.WARNING,
                        _(
                            "Details extracted via OpenGraph. "
                            "Issue Tracker may still be configured incorrectly!"
                        ),
                    )
                else:
                    messages.add_message(
                        request,
                        messages.SUCCESS,
                        _(
                            "Details extracted via API. Issue Tracker configuration looks good!"
                        ),
                    )

                messages.add_message(
                    request,
                    messages.INFO,
                    details,
                )
            except Exception:  # pylint: disable=broad-except
                messages.add_message(
                    request,
                    messages.ERROR,
                    _("Issue Tracker configuration check failed"),
                )
                # show the actual exception with traceback b/c it can help debug failures
                messages.add_message(
                    request,
                    messages.ERROR,
                    traceback.format_exc(),
                )


class TemplateAdminForm(forms.ModelForm):
    text = forms.CharField(
        widget=SimpleMDE(),
        required=True,
    )

    class Meta:
        model = Template
        fields = "__all__"

    class Media:
        js = [
            "js/bundle.js",
        ]


class TemplateAdmin(admin.ModelAdmin):
    form = TemplateAdminForm


class TestCaseFieldSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            _("Test Plan - Cases List"),
            {
                "description": _(
                    "Configure which test case fields are visible in Test Plan case list."
                ),
                "fields": (
                    "plan_show_status",
                    "plan_show_automated",
                    "plan_show_priority",
                    "plan_show_category",
                    "plan_show_product",
                    "plan_show_author",
                    "plan_show_default_tester",
                    "plan_show_reviewer",
                ),
            },
        ),
        (
            _("Test Run - Executions List"),
            {
                "description": _(
                    "Configure which test case and execution fields are visible in Test Run executions list."
                ),
                "fields": (
                    "run_show_status",
                    "run_show_automated",
                    "run_show_priority",
                    "run_show_category",
                    "run_show_product",
                    "run_show_author",
                    "run_show_default_tester",
                    "run_show_assignee",
                    "run_show_tested_by",
                    "run_show_bugs",
                    "run_show_tags",
                    "run_show_components",
                ),
            },
        ),
        (
            _("Test Case - Summary Card (row-cards-pf)"),
            {
                "description": _(
                    "Configure which fields are visible in the top summary card of Test Case (/case/<id>/)."
                ),
                "fields": (
                    "case_card_show_author",
                    "case_card_show_default_tester",
                    "case_card_show_product",
                    "case_card_show_category",
                    "case_card_show_status",
                    "case_card_show_priority",
                    "case_card_show_create_date",
                    "case_card_show_setup_duration",
                    "case_card_show_testing_duration",
                    "case_card_show_expected_duration",
                    "case_card_show_automated",
                    "case_card_show_script",
                    "case_card_show_arguments",
                    "case_card_show_requirement",
                    "case_card_show_extra_link",
                ),
            },
        ),
        (
            _("Test Plan - Summary Card (row-cards-pf)"),
            {
                "description": _(
                    "Configure which fields are visible in the top summary card of Test Plan (/plan/<id>/)."
                ),
                "fields": (
                    "plan_card_show_author",
                    "plan_card_show_create_date",
                    "plan_card_show_product",
                    "plan_card_show_version",
                    "plan_card_show_type",
                    "plan_card_show_extra_link",
                ),
            },
        ),
        (
            _("Test Run - Summary Card (row-cards-pf)"),
            {
                "description": _(
                    "Configure which fields are visible in the top summary card of Test Run (/run/<id>/)."
                ),
                "fields": (
                    "run_card_show_plan",
                    "run_card_show_product",
                    "run_card_show_version",
                    "run_card_show_build",
                    "run_card_show_manager",
                    "run_card_show_default_tester",
                    "run_card_show_planned_start",
                    "run_card_show_start_date",
                    "run_card_show_planned_stop",
                    "run_card_show_stop_date",
                ),
            },
        ),
    ]

    def has_add_permission(self, request):
        return not TestCaseFieldSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = TestCaseFieldSettings.get_settings()
        return HttpResponseRedirect(
            reverse("admin:testcases_testcasefieldsettings_change", args=[settings_obj.pk])
        )


admin.site.register(BugSystem, BugSystemAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(TestCase, TestCaseAdmin)
admin.site.register(TestCaseStatus, TestCaseStatusAdmin)
admin.site.register(Template, TemplateAdmin)
admin.site.register(TestCaseFieldSettings, TestCaseFieldSettingsAdmin)
