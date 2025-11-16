from django.urls import path, include

from . import views


urlpatterns = [
    path("", views.student_signin, name="student_signin"),
    path("login/", views.student_signin, name="student_signin"),
    path("signup/", views.student_signup, name="student_signup"),
    path("student/dashboard/", views.student_dashboard, name="student_dashboard"),
    path("student/dashboard/<str:page>/", views.student_dashboard, name="student_dashboard_page"),
    path("student/surveys/<int:assignment_id>/", views.student_take_survey, name="student_take_survey"),
    path("student/responses/<int:submission_id>/", views.student_view_response, name="student_view_response"),
    # path("teacher/", views.teacher_dashboard, name=""),
    path("teacher/login/", views.teacher_signin, name="teacher_signin"),
    path("teacher/builder/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/<str:page>/", views.teacher_dashboard, name="teacher_dashboard_page"),
    path("teacher/surveys/save/", views.teacher_save_survey, name="teacher_save_survey"),
    path("teacher/surveys/<int:survey_id>/preview/", views.teacher_preview_survey, name="teacher_preview_survey"),
    path("teacher/responses-history/", views.teacher_responses_history, name="teacher_responses_history"),
    path("teacher/surveys/<int:survey_id>/responses/", views.teacher_analytics, name="teacher_analytics"),
    path("logout/", views.logout_view, name="logout"),
    path("__reload/", include("django_browser_reload.urls"))
]
