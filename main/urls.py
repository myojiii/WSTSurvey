from django.urls import path

from . import views


urlpatterns = [
    path("", views.student_signin, name="student_signin"),
    path("login/", views.student_signin, name="student_signin"),
    path("signup/", views.student_signup, name="student_signup"),
]
