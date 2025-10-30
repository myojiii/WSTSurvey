from django.contrib.auth.models import User
from django.db import models


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    year_section = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.year_section})"
