from django.contrib.auth.models import User
from django.db import models


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    year_section = models.CharField(max_length=50) #need naka foreign key

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.year_section})"

#insert here nalang yung teacherprofile ende ko pa knows kung pano magadd admin hashhah

class ClassSection(models.Model):
    section_name = models.CharField(max_length=50)

    def __str__(self):
        return self.section_name

'''Survey Structure'''
class Survey(models.Model):
    #teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE) #yung user model ng teacher
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('draft', 'Draft'), ('published', 'Published'), ('closed', 'Closed')],
        default='draft'
    )

    def __str__(self):
        return self.title

class SurveyAssignment(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE)
    section = models.ForeignKey(ClassSection, on_delete=models.CASCADE)
    assigned_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('survey', 'section')

    def __str__(self):
        return f"{self.survey.title} → {self.section.section_name}"

'''BASE QUESTION AND SUBTYPES STRUCTURE'''
class Question(models.Model):
    QUESTION_TYPES = [
        ('MCQ', 'Multiple Choice'),
        ('LIKERT', 'Likert Scale'),
        ('SHORT', 'Short Answer'),
    ]
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
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

    def __str__(self):
        return f"{self.text} (Q{self.question_id})"

'''SUBMISSION AND ANSWERS'''
class SurveySubmission(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE) #tama ba studentprofile dapat yung ikey ditoo
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('survey', 'student')

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.survey.title}"


class Answer(models.Model):
    submission = models.ForeignKey(SurveySubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True)
    text_response = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Answer by {self.submission.student.user.get_full_name()} to {self.question.text[:30]}"