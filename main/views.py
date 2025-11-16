import json
from datetime import timedelta, datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST
from collections import Counter

import re
from collections import Counter
from io import BytesIO
from wordcloud import WordCloud, STOPWORDS
import base64

from .forms import StudentSigninForm, StudentSignupForm
from .models import (
    Answer,
    Choice,
    ClassSection,
    LikertQuestion,
    MCQQuestion,
    Question,
    ShortAnswerQuestion,
    StudentProfile,
    Survey,
    SurveyAssignment,
    SurveySubmission,
)


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


def _serialize_questions(question_qs):
    """Normalize question data for previews and student forms."""
    items = []
    for question in question_qs:
        entry = {
            "id": question.id,
            "title": question.text,
            "description": question.description,
            "type": question.question_type,
            "is_required": question.is_required,
            "order": question.order_number,
            "choices": [],
            "choice_texts": [],
            "scale_labels": [],
            "likert_pairs": [],
            "max_length": None,
        }

        if question.question_type == "MCQ":
            choices = list(
                question.choices.order_by("value", "id").values("id", "text")
            )
            entry["choices"] = choices
            entry["choice_texts"] = [choice["text"] for choice in choices]
        elif question.question_type == "LIKERT":
            choices = list(
                question.choices.order_by("value", "id").values("id", "text")
            )
            entry["choices"] = choices
            likert = getattr(question, "likertquestion", None)
            if likert and likert.scale_labels:
                entry["scale_labels"] = list(likert.scale_labels)
            else:
                entry["scale_labels"] = [choice["text"] for choice in choices]
            if not entry["scale_labels"]:
                entry["scale_labels"] = ["Disagree", "Agree"]
            for index, label in enumerate(entry["scale_labels"]):
                choice_id = ""
                if index < len(choices):
                    choice_id = str(choices[index]["id"])
                entry["likert_pairs"].append({"label": label, "choice_id": choice_id})
        else:  # SHORT
            short = getattr(question, "shortanswerquestion", None)
            entry["max_length"] = short.max_length if short else 500

        items.append(entry)
    return items


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


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
            section=form.cleaned_data["section"],
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

    assigned_surveys = []
    completed_surveys = []
    range_filter = request.GET.get("range", "all").lower()
    due_filter = request.GET.get("due", "all").lower()

    if profile.section:
        assignments_qs = SurveyAssignment.objects.filter(status="published", section=profile.section).select_related("survey", "survey__teacher")

        now = timezone.now()
        today = now.date()

        if range_filter == "today":
            assignments_qs = assignments_qs.filter(assigned_date__date=today)
        elif range_filter == "week":
            start_week = today - timedelta(days=today.weekday())
            assignments_qs = assignments_qs.filter(assigned_date__date__gte=start_week)
        elif range_filter == "month":
            assignments_qs = assignments_qs.filter(assigned_date__date__month=today.month, assigned_date__date__year=today.year)

        if due_filter == "today":
            assignments_qs = assignments_qs.filter(due_date=today)
        elif due_filter == "week":
            start_week = today - timedelta(days=today.weekday())
            assignments_qs = assignments_qs.filter(due_date__gte=start_week, due_date__lte=start_week + timedelta(days=6))
        elif due_filter == "month":
            assignments_qs = assignments_qs.filter(due_date__month=today.month, due_date__year=today.year)

        assignments = assignments_qs.order_by("-assigned_date", "-survey__updated_at")
        survey_ids = [assignment.survey_id for assignment in assignments]
        submission_map = {
            submission.survey_id: submission
            for submission in SurveySubmission.objects.filter(
                student=profile, survey_id__in=survey_ids
            )
        }
        for assignment in assignments:
            survey = assignment.survey
            teacher = survey.teacher
            teacher_name = "Administrator"
            if teacher:
                teacher_name = teacher.get_full_name() or teacher.username
            submission = submission_map.get(survey.id)
            if submission and submission.is_submitted:
                continue
            due_date = assignment.due_date or survey.due_date
            if due_date and timezone.is_naive(due_date):
                due_date = timezone.make_aware(due_date, timezone.get_default_timezone())
            effective_status = getattr(survey, "display_status", survey.status)
            is_closed = effective_status == "closed" or effective_status == "archived"
            status_label = "Closed" if is_closed else "Open"
            action_label = "Closed" if is_closed else ("Continue" if submission else "Take Survey")
            assigned_surveys.append(
                {
                    "assignment_id": assignment.id,
                    "survey_id": survey.id,
                    "title": survey.title,
                    "assigned_by": teacher_name,
                    "assigned_date": assignment.assigned_date or survey.created_at,
                    "due_date": due_date,
                    "status": status_label,
                    "has_submission": bool(submission),
                    "action_label": action_label,
                    "is_closed": is_closed,
                }
            )

        completed_submissions = (
            SurveySubmission.objects.filter(student=profile, is_submitted=True)
            .select_related("survey", "survey__teacher")
            .order_by("-submitted_at")
        )
        completed_ids = [submission.survey_id for submission in completed_submissions]
        assignment_map = {
            assignment.survey_id: assignment
            for assignment in SurveyAssignment.objects.filter(
                section=profile.section, survey_id__in=completed_ids
            ).select_related("section")
        }
        for submission in completed_submissions:
            survey = submission.survey
            assignment = assignment_map.get(submission.survey_id)
            teacher = survey.teacher
            teacher_name = "Administrator"
            if teacher:
                teacher_name = teacher.get_full_name() or teacher.username
            completed_surveys.append(
                {
                    "assignment_id": assignment.id if assignment else None,
                    "survey_id": survey.id,
                    "submission_id": submission.id,
                    "title": survey.title,
                    "assigned_by": teacher_name,
                    "assigned_date": (assignment.assigned_date if assignment else survey.created_at),
                    "due_date": (assignment.due_date if assignment else survey.due_date),
                    "submitted_at": submission.submitted_at,
                    "status": "Done",
                }
            )

    if page not in {"assigned", "responses"}:
        page = "assigned"

    student_nav = [
        {"slug": "assigned", "label": "Assigned Surveys", "icon": "📋"},
        {"slug": "responses", "label": "Response History", "icon": "🗂"},
    ]

    return render(
        request,
        "main/student_dashboard.html",
        {
            "profile": profile,
            "assigned_surveys": assigned_surveys,
            "completed_surveys": completed_surveys,
            "active_page": page,
            "nav_items": student_nav,
            "assigned_filters": {
                "range": range_filter,
                "due": due_filter,
            },
        },
    )


@login_required(login_url="student_signin")
def student_take_survey(request, assignment_id):
    """Allow a student to respond to a published survey assigned to their section."""
    if not hasattr(request.user, "student_profile"):
        if request.user.username == _teacher_username():
            return redirect("teacher_dashboard")
        return redirect("student_signin")

    profile = request.user.student_profile
    assignment = get_object_or_404(
        SurveyAssignment.objects.select_related("survey", "section", "survey__teacher"),
        id=assignment_id,
    )

    if not assignment.section or assignment.section_id != profile.section_id:
        return HttpResponseForbidden("You do not have access to this survey.")

    if assignment.status != "published" or assignment.survey.status != "published":
        raise Http404

    survey = assignment.survey
    question_qs = (
        survey.questions.order_by("order_number")
        .select_related("likertquestion", "shortanswerquestion")
        .prefetch_related("choices")
    )
    questions_payload = _serialize_questions(question_qs)
    payload_by_id = {item["id"]: item for item in questions_payload}

    existing_submission = (
        SurveySubmission.objects.filter(survey=survey, student=profile)
        .prefetch_related("answers__selected_choice")
        .first()
    )

    if existing_submission and existing_submission.is_submitted:
        messages.info(request, "You already submitted this survey. Viewing your responses instead.")
        return redirect("student_view_response", existing_submission.id)

    form_values = {}
    has_saved_progress = bool(existing_submission)
    if existing_submission:
        for answer in existing_submission.answers.all():
            key = str(answer.question_id)
            if answer.selected_choice_id:
                form_values[key] = str(answer.selected_choice_id)
            else:
                form_values[key] = answer.text_response or ""

    errors = {}

    if request.method == "POST":
        action = request.POST.get("action", "submit")
        require_complete = action == "submit"
        form_values = {}
        responses = {}
        has_any_response = False

        for question in question_qs:
            question_data = payload_by_id.get(question.id, {})
            field_name = f"q_{question.id}"
            submitted_value = request.POST.get(field_name, "")
            form_values[str(question.id)] = submitted_value

            if question.question_type in {"MCQ", "LIKERT"}:
                choice_map = {
                    str(choice.id): choice for choice in question.choices.all()
                }
                if not submitted_value:
                    if question.is_required and require_complete:
                        errors[question.id] = "Please choose an option."
                    continue
                choice = choice_map.get(submitted_value)
                if not choice:
                    errors[question.id] = "Select a valid option."
                    continue
                responses[question.id] = {"choice": choice}
                has_any_response = True
            else:
                text = submitted_value.strip()
                max_length = question_data.get("max_length") or 500
                if not text and question.is_required and require_complete:
                    errors[question.id] = "This question is required."
                    continue
                if text and len(text) > max_length:
                    errors[question.id] = f"Please keep your answer under {max_length} characters."
                    continue
                if text:
                    responses[question.id] = {"text": text}
                    has_any_response = True

        if action == "save" and not has_any_response:
            errors[None] = "Add at least one answer before saving your progress."

        if not errors:
            with transaction.atomic():
                submission, created = SurveySubmission.objects.get_or_create(
                    survey=survey,
                    student=profile,
                )
                submission.is_submitted = action == "submit"
                update_fields = ["is_submitted", "updated_at"]
                if submission.is_submitted:
                    submission.submitted_at = timezone.now()
                    update_fields.append("submitted_at")
                submission.save(update_fields=update_fields)

                submission.answers.all().delete()

                answer_objects = []
                for question in question_qs:
                    result = responses.get(question.id)
                    if not result:
                        continue
                    answer_objects.append(
                        Answer(
                            submission=submission,
                            question=question,
                            selected_choice=result.get("choice"),
                            text_response=result.get("text", ""),
                        )
                    )
                if answer_objects:
                    Answer.objects.bulk_create(answer_objects)

                if action == "save":
                    if _is_ajax(request):
                        return JsonResponse({"status": "saved"})
                    return redirect("student_dashboard")

            messages.success(request, "Your responses have been submitted.")
            return redirect("student_dashboard_page", page="responses")

    for item in questions_payload:
        key = str(item["id"])
        item["value"] = form_values.get(key, "")
        item["error"] = errors.get(item["id"])

    total_questions = len(questions_payload)
    answered_count = 0
    for item in questions_payload:
        if item["type"] in {"MCQ", "LIKERT"}:
            if item["value"]:
                answered_count += 1
        else:
            if item["value"].strip():
                answered_count += 1
    if total_questions:
        progress_percent = int((answered_count / total_questions) * 100)
    else:
        progress_percent = 0

    teacher = survey.teacher
    if teacher:
        teacher_name = teacher.get_full_name() or teacher.username
    else:
        teacher_name = "Administrator"

    return render(
        request,
        "main/student_take_survey.html",
        {
            "assignment": assignment,
            "survey": survey,
            "questions": questions_payload,
            "has_submission": existing_submission is not None,
            "has_saved_progress": has_saved_progress,
            "teacher_name": teacher_name,
            "form_errors": errors.get(None, ""),
            "answered_count": answered_count,
            "total_questions": total_questions,
            "progress_percent": progress_percent,
        },
    )


@login_required(login_url="student_signin")
def student_view_response(request, submission_id):
    # Allow both students and teachers to view responses
    is_teacher = request.user.username == _teacher_username()

    if not is_teacher and not hasattr(request.user, "student_profile"):
        return redirect("student_signin")

    # Get the submission
    submission_query = SurveySubmission.objects.select_related(
        "survey", "survey__teacher", "student", "student__user", "student__section"
    )

    if is_teacher:
        # Teacher can view any submission
        submission = get_object_or_404(
            submission_query,
            id=submission_id,
            is_submitted=True,
        )
    else:
        # Student can only view their own submission
        profile = request.user.student_profile
        submission = get_object_or_404(
            submission_query,
            id=submission_id,
            student=profile,
            is_submitted=True,
        )

    survey = submission.survey
    question_qs = (
        survey.questions.order_by("order_number")
        .select_related("likertquestion", "shortanswerquestion")
        .prefetch_related("choices")
    )
    questions_payload = _serialize_questions(question_qs)
    answers_map = {
        answer.question_id: answer
        for answer in submission.answers.select_related("selected_choice")
    }

    for item in questions_payload:
        answer = answers_map.get(item["id"])
        if item["type"] in {"MCQ", "LIKERT"}:
            selected_id = ""
            selected_text = ""
            if answer and answer.selected_choice:
                selected_id = str(answer.selected_choice_id)
                selected_text = answer.selected_choice.text
            item["selected_choice"] = selected_id
            item["selected_text"] = selected_text
        else:
            item["answer_text"] = answer.text_response if answer else ""

    teacher = survey.teacher
    if teacher:
        teacher_name = teacher.get_full_name() or teacher.username
    else:
        teacher_name = "Administrator"

    assignment = SurveyAssignment.objects.filter(
        section=submission.student.section, survey=survey
    ).select_related("section").first()

    return render(
        request,
        "main/student_view_response.html",
        {
            "survey": survey,
            "questions": questions_payload,
            "teacher_name": teacher_name,
            "assignment": assignment,
            "submission": submission,
            "is_teacher_viewing": is_teacher,
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
    surveys = Survey.objects.filter(teacher=request.user)

    # 2. Detect selected survey ID from GET
    selected_id = request.GET.get("survey_id")

    if selected_id:
        survey = surveys.filter(id=selected_id).prefetch_related("questions__choices").first()
    else:
        # Default: first survey
        survey = surveys.first()

    # Define statuses to exclude
    excluded_statuses = ["delete", "deleted", "archived", "archive"]

    # All surveys for the teacher excluding the above statuses
    collection_surveys = Survey.objects.filter(
        teacher=request.user
    ).exclude(status__in=excluded_statuses)

    # Total surveys (after exclusion)
    total_surveys = collection_surveys.count()

    # Active surveys (status == "Open")
    active_surveys = collection_surveys.filter(status="Open").count()

    # Total responses across all surveys (consider only non-excluded surveys)
    total_responses = SurveySubmission.objects.filter(survey__in=collection_surveys).count()

    submissions = []
    answers = []
    summary_list = []
    tempasd = 0
    survey_id = []
    collection_surveys = []

    collection_surveys = Survey.objects.filter(teacher=request.user)

    survey_title = "<Survey Title>"

    if page == "dashboard":
        selected_id = request.GET.get("survey_id")

        if selected_id:
            selected_id = int(selected_id)

        else:
            # Default: select the first survey in the list
            selected_id = collection_surveys.first().id

        # 2. Load the survey object based on selected ID
        survey = Survey.objects.filter(id=selected_id, teacher=request.user).first()



        collection_surveys = (
            Survey.objects.filter(teacher=request.user)
            .prefetch_related("assignments__section")
            .order_by("-updated_at")
        )


        if survey:
            survey_title = survey.title if survey else ""

            submissions = (
                SurveySubmission.objects
                .filter(survey=survey)
                .select_related("student__user")
                .prefetch_related("answers__question", "answers__selected_choice")
            )


            # flatten answers
            for submission in submissions:
                answers.extend(submission.answers.all())
                tempasd = tempasd+1

            # Build summaries
            for question in survey.questions.all():

                question_answers = [a for a in answers if a.question_id == question.id]

                if question.question_type in ["MCQ", "LIKERT"]:
                    choice_counts = {c.text: 0 for c in question.choices.all()}

                    for a in question_answers:
                        if a.selected_choice:
                            choice_counts[a.selected_choice.text] += 1

                    summary_list.append({
                        "question": question,
                        "type": question.question_type,
                        "choices": list(choice_counts.items()),
                        "choice_labels": list(choice_counts.keys()),
                        "choice_values": list(choice_counts.values()),
                        "response_count": len(question_answers)
                    })

                elif question.question_type == "SHORT":
                    short_texts_orig = [a.text_response for a in question_answers if a.text_response]

                    summary_entry = {
                        "question": question,
                        "type": "SHORT",
                        "short_answers_orig": short_texts_orig,
                        "response_count": len(short_texts_orig),
                    }

                    # Generate wordcloud if there are answers
                    if short_texts_orig:
                        short_texts_clean = [t.strip().lower() for t in short_texts_orig]
                        text_blob = " ".join(short_texts_clean)
                        words = re.findall(r"\b[^\d\W]\w+\b", text_blob)

                        stopwords = set(STOPWORDS)
                        filtered = [w for w in words if w not in stopwords and len(w) > 2]
                        freqs = Counter(filtered) or {"(no responses)": 1}

                        wc = WordCloud(width=800, height=400, background_color="white",
                                       collocations=False, max_words=200).generate_from_frequencies(freqs)

                        buffer = BytesIO()
                        wc.to_image().save(buffer, format="PNG")
                        img_b64 = base64.b64encode(buffer.getvalue()).decode()
                        summary_entry["wordcloud_b64"] = img_b64

                        summary_list.append(summary_entry)
                    print(f"Question {question.id}: {len(question_answers)} answers")
    """Simple landing page for the teacher account."""
    if request.user.username != _teacher_username():
        if hasattr(request.user, "student_profile"):
            return redirect("student_dashboard")
        return redirect("student_signin")

    page = page.lower()
    allowed_pages = {"dashboard", "collection", "history", "new"}
    if page not in allowed_pages:
        page = "new"

    teacher_nav = [
        {"slug": "dashboard", "label": "Dashboard", "icon": "📊"},
        {"slug": "collection", "label": "Survey Collection", "icon": "📚"},
        {"slug": "history", "label": "Responses History", "icon": "📁"},
        {"slug": "new", "label": "Survey Builder", "icon": "➕"},
    ]

    try:
        ClassSection.ensure_seeded()
        sections = ClassSection.objects.order_by("section_id")
    except Exception:
        letters = ["A", "B", "C", "D"]
        sections = [
            ClassSection(section_id=f"{year}{letter}", year=year)
            for year in range(1, 5)
            for letter in letters
        ]

        # collection_surveys = (
        #     Survey.objects.filter(teacher=request.user)
        #     .prefetch_related("assignments__section")
        #     .order_by("-updated_at")
        # )

    # Handle Responses History page
    responses_data = None
    paginator = None
    all_sections = []

    if page == "history":
        responses = SurveySubmission.objects.filter(
            is_submitted=True
        ).select_related(
            'student__user', 'student__section', 'survey'
        ).order_by('-submitted_at')

        # Get all unique sections for the filter dropdown
        all_sections = ClassSection.objects.order_by("section_id")

        # Search by student name only (first name or last name)
        search_student = request.GET.get('search_student', '').strip()
        if search_student:
            responses = responses.filter(
                Q(student__user__first_name__icontains=search_student) |
                Q(student__user__last_name__icontains=search_student)
            )

        # Search by survey title
        search_survey = request.GET.get('search_survey', '').strip()
        if search_survey:
            responses = responses.filter(
                Q(survey__title__icontains=search_survey)
            )

        # Filter by section
        filter_section = request.GET.get('filter_section', '').strip()
        if filter_section:
            responses = responses.filter(student__section__section_id=filter_section)

        # Filter by date range
        date_from = request.GET.get('date_from', '').strip()
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                responses = responses.filter(submitted_at__date__gte=date_from_obj.date())
            except ValueError:
                pass

        date_to = request.GET.get('date_to', '').strip()
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                responses = responses.filter(submitted_at__date__lte=date_to_obj.date())
            except ValueError:
                pass

        # Pagination
        paginator = Paginator(responses, 10)
        page_number = request.GET.get('page', 1)
        responses_data = paginator.get_page(page_number)

    editing_payload = None
    if page == "new":
        survey_param = request.GET.get("survey")
        survey_to_edit = None
        if survey_param:
            try:
                survey_id = int(survey_param)
            except (TypeError, ValueError):
                survey_id = None
            if survey_id:
                survey_to_edit = (
                    Survey.objects.filter(id=survey_id, teacher=request.user)
                    .prefetch_related("assignments__section")
                    .first()
                )
        if survey_to_edit:
            questions_data = []
            type_mapping = {
                "MCQ": "multiple_choice",
                "LIKERT": "likert",
                "SHORT": "short_text",
            }
            questions_qs = (
                survey_to_edit.questions.order_by("order_number")
                .select_related("mcqquestion", "likertquestion", "shortanswerquestion")
                .prefetch_related("choices")
            )
            for question in questions_qs:
                builder_type = type_mapping.get(question.question_type, "short_text")
                question_info = {
                    "id": question.id,
                    "question_type": builder_type,
                    "title": question.text,
                    "is_required": question.is_required,
                    "order": question.order_number,
                }
                if builder_type == "multiple_choice":
                    choices = list(
                        question.choices.order_by("value", "id").values_list("text", flat=True)
                    )
                    while len(choices) < 2:
                        choices.append("")
                    question_info["choices"] = choices
                elif builder_type == "likert":
                    likert = getattr(question, "likertquestion", None)
                    labels = []
                    if likert and likert.scale_labels:
                        labels = list(likert.scale_labels)
                    else:
                        labels = list(
                            question.choices.order_by("value", "id").values_list("text", flat=True)
                        )
                    while len(labels) < 2:
                        labels.append("")
                    question_info["scale_labels"] = labels
                else:
                    short = getattr(question, "shortanswerquestion", None)
                    question_info["max_length"] = short.max_length if short else 500
                questions_data.append(question_info)

            section_ids = [
                assignment.section.section_id
                for assignment in survey_to_edit.assignments.all()
                if assignment.section
            ]

            due_date_value = ""
            if survey_to_edit.due_date:
                due_reference = survey_to_edit.due_date
                if timezone.is_naive(due_reference):
                    due_reference = timezone.make_aware(due_reference, timezone.get_default_timezone())
                due_local = timezone.localtime(due_reference)
                due_date_value = due_local.strftime("%Y-%m-%dT%H:%M")

            editing_payload = {
                "id": survey_to_edit.id,
                "title": survey_to_edit.title,
                "description": survey_to_edit.description or "",
                "due_date": due_date_value,
                "sections": section_ids,
                "questions": questions_data,
                "status": survey_to_edit.display_status,
            }
    return render(
        request,
        "main/teacher_dashboard.html",
        {
            "teacher": request.user,
            "active_page": page,
            "nav_items": teacher_nav,
            "sections": sections,
            "collection_surveys": collection_surveys,
            "editing_payload": editing_payload,
            "responses": responses_data,
            "paginator": paginator,
            "all_sections": all_sections,
            "surveys": surveys,
            "survey": survey,
            "summary_list": summary_list,
            "submissions": submissions,
            "selected_id": selected_id,

            "selected_survey_id": selected_id,
            "survey_title": survey_title,
    "total_surveys": total_surveys,
    "active_surveys": active_surveys,
    "total_responses": total_responses,

        },
    )


@require_POST
@login_required(login_url="student_signin")
def teacher_save_survey(request):
    if request.user.username != _teacher_username():
        return HttpResponseForbidden("Only the teacher account can create surveys.")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    status = payload.get("status", "draft")
    if status not in {"draft", "published"}:
        return JsonResponse({"error": "Invalid survey status."}, status=400)

    availability = (payload.get("availability") or "open").lower()
    if availability not in {"open", "closed"}:
        return JsonResponse({"error": "Invalid availability option."}, status=400)

    final_status = status
    if status == "published" and availability == "closed":
        final_status = "closed"

    title = (payload.get("title") or "").strip()
    if not title:
        return JsonResponse({"error": "Please provide a survey title."}, status=400)

    description = (payload.get("description") or "").strip()
    due_date_str = payload.get("due_date")
    due_date = parse_datetime(due_date_str) if due_date_str else None
    if due_date_str and due_date is None:
        return JsonResponse({"error": "Invalid due date format."}, status=400)
    if due_date and timezone.is_naive(due_date):
        due_date = timezone.make_aware(due_date, timezone.get_default_timezone())

    section_ids = payload.get("sections") or []
    ClassSection.ensure_seeded()
    sections_map = {section.section_id: section for section in ClassSection.objects.filter(section_id__in=section_ids)}

    if status == "published" and len(sections_map) != len(section_ids):
        return JsonResponse({"error": "One or more selected sections could not be found."}, status=400)

    questions_payload = payload.get("questions") or []
    if status == "published" and not questions_payload:
        return JsonResponse({"error": "Add at least one question before publishing."}, status=400)

    survey_id = payload.get("survey_id")

    with transaction.atomic():
        if survey_id:
            survey = get_object_or_404(Survey, id=survey_id)
            if survey.teacher and survey.teacher != request.user:
                return HttpResponseForbidden("You do not have permission to edit this survey.")
        else:
            survey = Survey(teacher=request.user)

        survey.teacher = request.user
        survey.title = title
        survey.description = description
        survey.due_date = due_date
        survey.status = final_status
        if status == "published":
            survey.published_at = timezone.now()
        else:
            survey.published_at = None
        survey.save()

        # Synchronize assignments
        existing_assignments = {assign.section.section_id: assign for assign in survey.assignments.all() if assign.section}
        keep_ids = set()

        for section_id in section_ids:
            section = sections_map.get(section_id)
            if not section:
                continue
            assignment = existing_assignments.get(section_id)
            if not assignment:
                assignment = SurveyAssignment(survey=survey, section=section)
            assignment.section = section
            assignment.status = "published" if status == "published" else "draft"
            assignment.due_date = due_date
            assignment.assigned_date = timezone.now() if status == "published" else None
            assignment.save()
            keep_ids.add(section_id)

        if keep_ids:
            survey.assignments.exclude(section__section_id__in=keep_ids).delete()
        else:
            survey.assignments.all().delete()

        # Rebuild question set
        survey.questions.all().delete()

        type_mapping = {
            "multiple_choice": "MCQ",
            "likert": "LIKERT",
            "short_text": "SHORT",
        }

        for index, question_data in enumerate(questions_payload, start=1):
            raw_type = question_data.get("question_type")
            question_type = type_mapping.get(raw_type)
            if not question_type:
                continue

            question_text = (question_data.get("title") or "Untitled Question").strip()
            question = Question.objects.create(
                survey=survey,
                text=question_text or "Untitled Question",
                description=question_data.get("description", ""),
                question_type=question_type,
                order_number=index,
                is_required=bool(question_data.get("is_required", False)),
            )

            if question_type == "MCQ":
                MCQQuestion.objects.create(question=question, randomize_choices=bool(question_data.get("randomize", False)))
                choices = [choice.strip() for choice in (question_data.get("choices") or []) if choice.strip()]
                for order, choice_text in enumerate(choices, start=1):
                    Choice.objects.create(question=question, text=choice_text, value=order)
            elif question_type == "LIKERT":
                labels = [label.strip() for label in (question_data.get("scale_labels") or []) if label.strip()]
                if len(labels) < 2:
                    labels = ["Disagree", "Agree"]
                scale_min = 1
                scale_max = scale_min + len(labels) - 1
                LikertQuestion.objects.create(question=question, scale_min=scale_min, scale_max=scale_max, scale_labels=labels)
                for offset, label in enumerate(labels, start=scale_min):
                    Choice.objects.create(question=question, text=label, value=offset)
            else:  # SHORT
                max_length = question_data.get("max_length") or 500
                ShortAnswerQuestion.objects.create(question=question, max_length=max_length)

    return JsonResponse({"id": survey.id, "status": survey.display_status})


@login_required(login_url="student_signin")
def teacher_preview_survey(request, survey_id):
    survey = get_object_or_404(
        Survey.objects.prefetch_related("questions__choices", "assignments__section"),
        id=survey_id,
    )
    if survey.teacher and survey.teacher != request.user and request.user.username != _teacher_username():
        raise Http404

    question_qs = (
        survey.questions.order_by("order_number")
        .select_related("likertquestion", "shortanswerquestion")
        .prefetch_related("choices")
    )
    questions = _serialize_questions(question_qs)

    assigned_sections = survey.assignments.select_related("section")

    return render(
        request,
        "main/survey_preview.html",
        {
            "survey": survey,
            "questions": questions,
            "assigned_sections": assigned_sections,
            "is_preview": request.user.username == _teacher_username(),
        },
    )


@login_required(login_url="student_signin")
def teacher_analytics(request, survey_id):
    template = "main/teacher_analytics.html"
    survey = (
        Survey.objects
        .filter(teacher=request.user, id=survey_id)
        .prefetch_related("questions__choices")
        .first()
    )

    submissions = []
    answers = []
    summary_list = []

    if survey:
        submissions = (
            SurveySubmission.objects
            .filter(survey=survey)
            .select_related("student__user")
            .prefetch_related("answers__question", "answers__selected_choice")
        )

        for submission in submissions:
            for answer in submission.answers.all():
                answers.append(answer)

        print(len(submissions))
        print(len(answers))

        # make summary grouped by question type
        for question in survey.questions.all():
            question_answers = [a for a in answers if a.question_id == question.id]

            if question.question_type in ["MCQ", "LIKERT"]:
                # Start with all choices set to 0
                choice_counts = {c.text: 0 for c in question.choices.all()}

                # Count actual responses
                for a in question_answers:
                    if a.selected_choice:
                        choice_counts[a.selected_choice.text] += 1

                # Convert dict to lists for chart display
                choice_labels = list(choice_counts.keys())
                choice_values = list(choice_counts.values())

                summary_list.append({
                    "question": question,
                    "type": question.question_type,
                    "choices": list(choice_counts.items()),
                    "choice_labels": choice_labels,
                    "choice_values": choice_values,
                })



            elif question.question_type == "SHORT":
                # collect all text answers for this question
                short_texts_orig = [a.text_response for a in question_answers if a.text_response]  # original
                short_texts_clean = [a.text_response.strip().lower() for a in question_answers if
                                     a.text_response]  # cleaned for wordcloud

                summary_entry = {
                    "question": question,
                    "type": "SHORT",
                    "short_answers": short_texts_clean,  # for wordcloud
                    "short_answers_orig": short_texts_orig,  # for textarea
                }

                # build a combined string or frequency dict
                text_blob = " ".join(short_texts_clean)
                words = re.findall(r"\b[^\d\W]\w+\b", text_blob)  # simple word extractor

                # filter stopwords and very short words
                stopwords = set(STOPWORDS)
                filtered = [w for w in words if w not in stopwords and len(w) > 2]

                # build frequencies
                freqs = Counter(filtered) or {"(no responses)": 1}

                # generate wordcloud
                wc = WordCloud(
                    width=800,
                    height=400,
                    background_color="white",
                    collocations=False,
                    max_words=200
                ).generate_from_frequencies(freqs)

                # convert to base64
                buffer = BytesIO()
                wc.to_image().save(buffer, format="PNG")
                buffer.seek(0)
                img_b64 = base64.b64encode(buffer.read()).decode("utf-8")
                summary_entry["wordcloud_b64"] = img_b64

                summary_list.append(summary_entry)

            print(f"Question {question.id}: {len(question_answers)} answers")
            # for a in question_answers:
            #     print(f"- selected_choice: {a.selected_choice}, text_response: {a.text_response}")


    context = {
        "survey": survey,
        "submissions": submissions,
        "summary_list": summary_list,
    }

    return render(request, template, context)



def logout_view(request):
    """Log out any authenticated user and return to the sign-in screen."""
    if request.user.is_authenticated:
        auth_logout(request)
    return redirect("student_signin")


@login_required(login_url="student_signin")
def teacher_responses_history(request):
    """View all student responses with search and filter capabilities"""
    if request.user.username != _teacher_username():
        if hasattr(request.user, "student_profile"):
            return redirect("student_dashboard")
        return redirect("student_signin")

    # Get all submitted responses using SurveySubmission
    responses = SurveySubmission.objects.filter(
        is_submitted=True
    ).select_related(
        'student__user', 'survey'
    ).order_by('-submitted_at')

    # Search by student name
    search_student = request.GET.get('search_student', '').strip()
    if search_student:
        responses = responses.filter(
            Q(student__user__first_name__icontains=search_student) |
            Q(student__user__last_name__icontains=search_student)
        )

    # Filter by date range
    date_from = request.GET.get('date_from', '').strip()
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            responses = responses.filter(submitted_at__date__gte=date_from_obj.date())
        except ValueError:
            pass

    date_to = request.GET.get('date_to', '').strip()
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            responses = responses.filter(submitted_at__date__lte=date_to_obj.date())
        except ValueError:
            pass

    # Pagination
    paginator = Paginator(responses, 10)  # 10 responses per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'responses': page_obj,
        'paginator': paginator,
    }

    return render(request, 'main/teacher_responses_history.html', context)


@login_required(login_url="student_signin")
def teacher_view_student_response(request, submission_id):
    """Teacher view for viewing student responses"""
    if request.user.username != _teacher_username():
        if hasattr(request.user, "student_profile"):
            return redirect("student_dashboard")
        return redirect("student_signin")
    
    # Get the submission
    submission = get_object_or_404(
        SurveySubmission.objects.select_related(
            "survey", "survey__teacher", "student", "student__user", "student__section"
        ),
        id=submission_id,
        is_submitted=True,
    )

    survey = submission.survey
    question_qs = (
        survey.questions.order_by("order_number")
        .select_related("likertquestion", "shortanswerquestion")
        .prefetch_related("choices")
    )
    questions_payload = _serialize_questions(question_qs)
    answers_map = {
        answer.question_id: answer
        for answer in submission.answers.select_related("selected_choice")
    }

    for item in questions_payload:
        answer = answers_map.get(item["id"])
        if item["type"] in {"MCQ", "LIKERT"}:
            selected_id = ""
            selected_text = ""
            if answer and answer.selected_choice:
                selected_id = str(answer.selected_choice_id)
                selected_text = answer.selected_choice.text
            item["selected_choice"] = selected_id
            item["selected_text"] = selected_text
        else:
            item["answer_text"] = answer.text_response if answer else ""

    teacher = survey.teacher
    if teacher:
        teacher_name = teacher.get_full_name() or teacher.username
    else:
        teacher_name = "Administrator"

    return render(
        request,
        "main/teacher_view_student_response.html",
        {
            "survey": survey,
            "questions": questions_payload,
            "teacher_name": teacher_name,
            "submission": submission,
        },
    )
