# Generated by Django 5.1.7 on 2025-03-16 15:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('papers', '0021_remove_submission_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='final_sent',
            field=models.BooleanField(default=False),
        ),
    ]
