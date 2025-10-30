from django.urls import path

from . import views


urlpatterns = [
    path("", views.student_signin, name="student_signin"),
    path("login/", views.student_signin, name="student_signin"),
    path("signup/", views.student_signup, name="student_signup"),
    path("student/dashboard/", views.student_dashboard, name="student_dashboard"),
    path("teacher/login/", views.teacher_signin, name="teacher_signin"),
    path("teacher/dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
    path("logout/", views.logout_view, name="logout"),
]
