from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0004_alter_survey_options_alter_surveyassignment_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="surveysubmission",
            name="is_submitted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="surveysubmission",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
