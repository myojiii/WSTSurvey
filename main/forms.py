from django import forms
from django.contrib.auth.models import User


YEAR_CHOICES = [
    ("", "Select year"),
    ("1st Year", "1st Year"),
    ("2nd Year", "2nd Year"),
    ("3rd Year", "3rd Year"),
    ("4th Year", "4th Year"),
]

SECTION_CHOICES = [
    ("", "Select section"),
    ("A", "Section A"),
    ("B", "Section B"),
    ("C", "Section C"),
    ("D", "Section D"),
    ("E", "Section E"),
    ("F", "Section F"),
    ("G", "Section G"),
    ("H", "Section H"),
    ("I", "Section I"),
]

GROUP_CHOICES = [
    ("", "Select group"),
    ("1", "Group 1"),
    ("2", "Group 2"),
]


class StudentSignupForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    year = forms.ChoiceField(choices=YEAR_CHOICES)
    section = forms.ChoiceField(choices=SECTION_CHOICES)
    group = forms.ChoiceField(choices=GROUP_CHOICES)

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
        value = self.cleaned_data.get("year", "").strip()
        if not value:
            raise forms.ValidationError("Please select your year level.")
        return value

    def clean_section(self):
        value = self.cleaned_data.get("section", "").strip()
        if not value:
            raise forms.ValidationError("Please select your section.")
        return value

    def clean_group(self):
        value = self.cleaned_data.get("group", "").strip()
        if not value:
            raise forms.ValidationError("Please select your group.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        year = cleaned_data.get("year")
        section = cleaned_data.get("section")
        group = cleaned_data.get("group")
        if year and section and group:
            cleaned_data["year_section"] = f"{year} - Section {section} - Group {group}"

        return cleaned_data


class StudentSigninForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        return self.cleaned_data["email"].lower()
