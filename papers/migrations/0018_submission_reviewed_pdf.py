# Generated by Django 5.1.7 on 2025-03-14 20:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('papers', '0017_alter_reviewer_interests'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='reviewed_pdf',
            field=models.FileField(blank=True, null=True, upload_to='reviewed/'),
        ),
    ]
