from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from .forms import StudentSigninForm, StudentSignupForm
from .models import StudentProfile


def _teacher_username() -> str:
    return settings.DEFAULT_TEACHER_EMAIL.lower()


def _ensure_teacher_account() -> User:
    username = _teacher_username()
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": settings.DEFAULT_TEACHER_EMAIL,
            "first_name": settings.DEFAULT_TEACHER_FIRST_NAME,
            "last_name": settings.DEFAULT_TEACHER_LAST_NAME,
            "is_staff": True,
        },
    )

    updated_fields = []

    if user.email != settings.DEFAULT_TEACHER_EMAIL:
        user.email = settings.DEFAULT_TEACHER_EMAIL
        updated_fields.append("email")

    if user.first_name != settings.DEFAULT_TEACHER_FIRST_NAME:
        user.first_name = settings.DEFAULT_TEACHER_FIRST_NAME
        updated_fields.append("first_name")

    if user.last_name != settings.DEFAULT_TEACHER_LAST_NAME:
        user.last_name = settings.DEFAULT_TEACHER_LAST_NAME
        updated_fields.append("last_name")

    if not user.is_staff:
        user.is_staff = True
        updated_fields.append("is_staff")

    if created or not user.check_password(settings.DEFAULT_TEACHER_PASSWORD):
        user.set_password(settings.DEFAULT_TEACHER_PASSWORD)
        updated_fields.append("password")

    if updated_fields:
        user.save(update_fields=updated_fields)

    return user


def student_signin(request):
    """Display and process the student sign-in form."""
    teacher_user = _ensure_teacher_account()

    if request.user.is_authenticated:
        if request.user.username == teacher_user.username:
            return redirect("teacher_dashboard")
        if hasattr(request.user, "student_profile"):
            return redirect("student_dashboard")

    form = StudentSigninForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )

        if user is None:
            form.add_error(None, "Invalid email or password.")
        elif user.username == teacher_user.username:
            login(request, user)
            return redirect("teacher_dashboard")
        elif hasattr(user, "student_profile"):
            login(request, user)
            return redirect("student_dashboard")
        else:
            form.add_error(None, "This account does not have student access.")

    return render(
        request,
        "main/student_signin.html",
        {
            "active_view": "signin",
            "form": form,
            "teacher_email": settings.DEFAULT_TEACHER_EMAIL,
        },
    )


def student_signup(request):
    """Display and process the student sign-up form."""
    if request.user.is_authenticated and hasattr(request.user, "student_profile"):
        return redirect("student_dashboard")

    form = StudentSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            username=form.cleaned_data["email"],
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"].strip(),
            last_name=form.cleaned_data["last_name"].strip(),
            password=form.cleaned_data["password"],
        )
        StudentProfile.objects.create(
            user=user,
            year_section=form.cleaned_data.get(
                "year_section",
                f"{form.cleaned_data['year']} - Section {form.cleaned_data['section']}",
            ),
        )
        login(request, user)
        return redirect("student_dashboard")

    return render(
        request,
        "main/student_signup.html",
        {"active_view": "signup", "form": form},
    )


@login_required(login_url="student_signin")
def student_dashboard(request, page="assigned"):
    """Landing page for authenticated students."""
    if not hasattr(request.user, "student_profile"):
        if request.user.username == _teacher_username():
            return redirect("teacher_dashboard")
        return redirect("student_signin")

    page = page.lower()
    profile = request.user.student_profile
    assigned_surveys = [
        {
            "id": idx,
            "title": title,
            "assigned_by": author,
            "date_submitted": submitted,
            "due_date": due,
        }
        for idx, (title, author, submitted, due) in enumerate(
            [
                ("Facilities Feedback", "Reymark Mendoza", "2025-10-15", "2025-10-24"),
                ("Student Satisfaction Survey", "Jhen Serrano", "2025-10-08", "2025-10-21"),
                ("Midterm Course Evaluation", "Jelaine Absalon", "2025-10-02", "2025-10-10"),
                ("End-Term Survey", "Maurice Joy Ramos", "2025-09-06", "2025-10-03"),
                ("Teacher Evaluation", "Mr. Dela Rosa", "2025-08-24", "2025-09-04"),
                ("Student Wellness Survey", "Abi Castilla", "2025-08-21", "2025-09-01"),
                ("Peer Evaluation", "Lawrence Velasco", "2025-08-17", "2025-08-29"),
                ("Class Feedback", "Duke Valencia", "2025-07-15", "2025-07-27"),
            ],
            start=1,
        )
    ]

    response_history = [
        {
            "survey": "Facilities Feedback",
            "submitted": "2025-10-15",
            "status": "Submitted",
        },
        {
            "survey": "Student Satisfaction Survey",
            "submitted": "2025-10-08",
            "status": "Submitted",
        },
    ]

    if page not in {"assigned", "responses"}:
        page = "assigned"

    student_nav = [
        {"slug": "assigned", "label": "Assigned Surveys", "icon": "📋"},
        {"slug": "responses", "label": "My Responses", "icon": "🗂"},
    ]

    return render(
        request,
        "main/student_dashboard.html",
        {
            "profile": profile,
            "assigned_surveys": assigned_surveys,
            "response_history": response_history,
            "active_page": page,
            "nav_items": student_nav,
        },
    )


def teacher_signin(request):
    """Redirect teachers to the unified sign-in screen after ensuring the account exists."""
    teacher_user = _ensure_teacher_account()
    if request.user.is_authenticated and request.user.username == teacher_user.username:
        return redirect("teacher_dashboard")
    return redirect("student_signin")


@login_required(login_url="student_signin")
def teacher_dashboard(request, page="new"):
    """Simple landing page for the teacher account."""
    if request.user.username != _teacher_username():
        if hasattr(request.user, "student_profile"):
            return redirect("student_dashboard")
        return redirect("student_signin")

    page = page.lower()
    if page not in {"assigned", "take", "history", "new"}:
        page = "new"

    teacher_nav = [
        {"slug": "assigned", "label": "Assigned Surveys", "icon": "📊"},
        {"slug": "take", "label": "Take Survey", "icon": "🧩"},
        {"slug": "history", "label": "Responses History", "icon": "📁"},
        {"slug": "new", "label": "New Survey", "icon": "➕"},
    ]

    return render(
        request,
        "main/teacher_dashboard.html",
        {
            "teacher": request.user,
            "active_page": page,
            "nav_items": teacher_nav,
        },
    )


def logout_view(request):
    """Log out any authenticated user and return to the sign-in screen."""
    if request.user.is_authenticated:
        auth_logout(request)
    return redirect("student_signin")
