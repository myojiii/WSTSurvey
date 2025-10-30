from django.urls import path

from . import views


urlpatterns = [
    path("", views.student_signin, name="student_signin"),
    path("login/", views.student_signin, name="student_signin"),
    path("signup/", views.student_signup, name="student_signup"),
    path("student/dashboard/", views.student_dashboard, name="student_dashboard"),
    path("student/dashboard/<str:page>/", views.student_dashboard, name="student_dashboard_page"),
    path("teacher/login/", views.teacher_signin, name="teacher_signin"),
    path("teacher/dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/dashboard/<str:page>/", views.teacher_dashboard, name="teacher_dashboard_page"),
    path("logout/", views.logout_view, name="logout"),
]
