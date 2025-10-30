from django.shortcuts import render


def student_signin(request):
    """Render the student sign-in screen."""
    return render(request, "main/student_signin.html", {"active_view": "signin"})


def student_signup(request):
    """Render the student sign-up screen."""
    return render(request, "main/student_signup.html", {"active_view": "signup"})
