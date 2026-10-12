from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from tcms.core.admin import ObjectPermissionsAdminMixin

from .models import (
    CaseWorkflow,
    CustomField,
    CycleRun,
    ExecutionResult,
    ExecutionSnapshot,
    Milestone,
    RunMilestone,
    SharedStepSet,
    TestCycle,
)


class HistoryAdmin(ObjectPermissionsAdminMixin, SimpleHistoryAdmin):
    pass


class DefinitionAdmin(HistoryAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


class AppendOnlyAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from tcms.testcases.models import TestCase

        from .services import visible, visible_executions, visible_runs

        queryset = super().get_queryset(request)
        if self.model in (ExecutionResult, ExecutionSnapshot):
            return queryset.filter(execution__in=visible_executions(request.user))
        if self.model == CaseWorkflow:
            return queryset.filter(
                case__in=visible(request.user, TestCase, "testcases.view_testcase")
            )
        queryset = queryset.filter(run__in=visible_runs(request.user))
        if self.model == CycleRun:
            return queryset.filter(
                cycle__in=visible(request.user, TestCycle, "workflow.view_testcycle")
            )
        return queryset.filter(
            milestone__in=visible(request.user, Milestone, "workflow.view_milestone")
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Milestone, HistoryAdmin)
admin.site.register(TestCycle, HistoryAdmin)
admin.site.register(SharedStepSet, DefinitionAdmin)
admin.site.register(CustomField, DefinitionAdmin)
admin.site.register(CaseWorkflow, AppendOnlyAdmin)
admin.site.register(ExecutionResult, AppendOnlyAdmin)
admin.site.register(ExecutionSnapshot, AppendOnlyAdmin)
admin.site.register(CycleRun, AppendOnlyAdmin)
admin.site.register(RunMilestone, AppendOnlyAdmin)
