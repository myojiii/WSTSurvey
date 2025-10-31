from django import forms
from django.contrib.auth.models import User
from django.db.utils import OperationalError

from .models import ClassSection


class StudentSignupForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    year = forms.ChoiceField(choices=[("", "Select year")])
    section = forms.ChoiceField(choices=[("", "Select section")])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            ClassSection.ensure_seeded()
            sections = list(ClassSection.objects.order_by("section_id"))
        except Exception:
            letters = ["A", "B", "C", "D"]
            sections = [
                ClassSection(section_id=f"{year}{letter}", year=year)
                for year in range(1, 5)
                for letter in letters
            ]

        years = sorted({section.year for section in sections})
        self.fields["year"].choices = [("", "Select year")] + [(str(y), str(y)) for y in years]
        self.fields["section"].choices = [("", "Select section")] + [
            (section.section_id, section.display_label) for section in sections
        ]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_first_name(self):
        first_name = self.cleaned_data["first_name"].strip()
        if not first_name:
            raise forms.ValidationError("Please enter your first name.")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data["last_name"].strip()
        if not last_name:
            raise forms.ValidationError("Please enter your last name.")
        return last_name

    def clean_year(self):
        value = (self.cleaned_data.get("year") or "").strip()
        if not value:
            raise forms.ValidationError("Please select your year level.")
        return value

    def clean_section(self):
        section_id = (self.cleaned_data.get("section") or "").strip()
        year = self.cleaned_data.get("year")
        if not section_id:
            raise forms.ValidationError("Please select your section.")
        try:
            section = ClassSection.objects.get(section_id=section_id)
        except ClassSection.DoesNotExist:
            ClassSection.ensure_seeded()
            try:
                section = ClassSection.objects.get(section_id=section_id)
            except ClassSection.DoesNotExist:
                raise forms.ValidationError("Unknown section selected.")
        except OperationalError:
            raise forms.ValidationError("Section data is unavailable. Please contact the administrator to run migrations.")
        if year and str(section.year) != str(year):
            raise forms.ValidationError("Selected section does not belong to the chosen year.")
        return section

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data


class StudentSigninForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        return self.cleaned_data["email"].lower()
