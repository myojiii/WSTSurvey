from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ClassSection(models.Model):
    """Homeroom section grouping students by year and subsection."""

    section_id = models.CharField(max_length=2, primary_key=True)
    year = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["section_id"]

    def __str__(self):
        return f"Year {self.year} · Section {self.section_id[-1]}"

    @property
    def display_label(self):
        return f"Year {self.year} - Section {self.section_id[-1]}"

    @classmethod
    def ensure_seeded(cls):
        """Create the default 1A-4D sections if they are missing."""
        if cls.objects.exists():
            return
        letters = ["A", "B", "C", "D"]
        sections = [
            cls(section_id=f"{year}{letter}", year=year)
            for year in range(1, 5)
            for letter in letters
        ]
        cls.objects.bulk_create(sections, ignore_conflicts=True)

class ClassSection(models.Model):
    section_id = models.CharField(max_length=2, primary_key=True)
    year_level = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.section_id} (Year {self.year_level})"

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
<<<<<<< HEAD
    section = models.ForeignKey(
        ClassSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.section_label})"

    @property
    def section_label(self):
        if self.section:
            return self.section.display_label
        return "Unassigned"
=======
    # year_section = models.CharField(max_length=50) #need naka foreign key
    section_id = models.ForeignKey(ClassSection, on_delete=models.CASCADE, null=True,blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.section_id})"
>>>>>>> c9a960985e600962c7bbb673b221c633057d084e

class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    class_sections = models.ManyToManyField(ClassSection, related_name="teachers", blank=True)

    def __str__(self):
        return self.user.get_full_name()

'''Survey Structure'''
class Survey(models.Model):
<<<<<<< HEAD
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("closed", "Closed"),
    ]

    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="teacher_surveys", null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
=======
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, null=True,blank=True) #yung user model ng teacher
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('draft', 'Draft'), ('published', 'Published'), ('closed', 'Closed'), ('archived', 'Archived')],
        default='draft'
    )
    assigned_sections = models.ManyToManyField(ClassSection, through='SurveyAssignment', related_name='surveys')
>>>>>>> c9a960985e600962c7bbb673b221c633057d084e

    def __str__(self):
        return self.title

class SurveyAssignment(models.Model):
<<<<<<< HEAD
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
    ]

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="assignments")
    section = models.ForeignKey(ClassSection, on_delete=models.CASCADE, related_name="assignments", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    assigned_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("survey", "section")
        ordering = ["section__section_id"]

    def __str__(self):
        section_label = self.section.section_id if self.section else "Unassigned"
        return f"{self.survey.title} → {section_label} ({self.status})"
=======
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE)
    section = models.ForeignKey(ClassSection, on_delete=models.CASCADE)
    assigned_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('survey', 'section')

    def __str__(self):
        return f"{self.survey.title} → {self.section.section_id}"
>>>>>>> c9a960985e600962c7bbb673b221c633057d084e

'''BASE QUESTION AND SUBTYPES STRUCTURE'''
class Question(models.Model):
    QUESTION_TYPES = [
        ('MCQ', 'Multiple Choice'),
        ('LIKERT', 'Likert Scale'),
        ('SHORT', 'Short Answer'),
    ]
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    description = models.TextField(blank=True)
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES)
    order_number = models.IntegerField(default=0)
    is_required = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.text[:40]}..."


# SUBTYPE: MCQ
class MCQQuestion(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, primary_key=True)
    randomize_choices = models.BooleanField(default=False)

    def __str__(self):
        return f"MCQ: {self.question.text[:40]}"


# SUBTYPE: Likert
class LikertQuestion(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, primary_key=True)
    scale_min = models.IntegerField(default=1)
    scale_max = models.IntegerField(default=5)
    scale_labels = models.JSONField(default=list, blank=True)  # para sa labeling ng 1–5

    def __str__(self):
        return f"Likert: {self.question.text[:40]}"


# SUBTYPE: Short Answer
class ShortAnswerQuestion(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, primary_key=True)
    max_length = models.IntegerField(default=500)

    def __str__(self):
        return f"Short: {self.question.text[:40]}"

'''CHOICE TABLE (Gamit ng MCQ and Likert)'''
class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    value = models.IntegerField(null=True, blank=True)  # for Likert numerical value
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.text} (Q{self.question_id})"

'''SUBMISSION AND ANSWERS'''
class SurveySubmission(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE) #tama ba studentprofile dapat yung ikey ditoo
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_submitted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('survey', 'student')

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.survey.title}"


class Answer(models.Model):
    submission = models.ForeignKey(SurveySubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True) #used by likert and mcq
    text_response = models.TextField(blank=True, null=True) #used for short question

    def __str__(self):
        return f"Answer by {self.submission.student.user.get_full_name()} to {self.question.text[:30]}"
