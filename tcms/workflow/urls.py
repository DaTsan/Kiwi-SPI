from django.urls import path

from . import views

app_name = "workflow"
urlpatterns = [
    path("", views.hub, name="hub"),
    path("milestones/new/", views.milestone_edit, name="milestone-new"),
    path("milestones/<int:pk>/", views.milestone_detail, name="milestone"),
    path("milestones/<int:pk>/edit/", views.milestone_edit, name="milestone-edit"),
    path("cycles/new/", views.cycle_edit, name="cycle-new"),
    path("cycles/<int:pk>/", views.cycle_detail, name="cycle"),
    path("cycles/<int:pk>/edit/", views.cycle_edit, name="cycle-edit"),
    path("shared/new/", views.shared_edit, name="shared-new"),
    path("shared/<int:pk>/", views.shared_detail, name="shared"),
    path("shared/<int:pk>/edit/", views.shared_edit, name="shared-edit"),
    path("fields/new/", views.field_edit, name="field-new"),
    path("fields/<int:pk>/edit/", views.field_edit, name="field-edit"),
    path("cases/<int:pk>/", views.case_detail, name="case"),
    path("executions/<int:pk>/", views.execution_detail, name="execution"),
    path("runs/<int:pk>/", views.run_detail, name="run"),
    path("todo/", views.todo, name="todo"),
    path("reports/", views.report, name="report"),
]
