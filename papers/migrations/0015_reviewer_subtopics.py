# Generated by Django 5.1.7 on 2025-03-13 18:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('papers', '0014_alter_domain_subtopics'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewer',
            name='subtopics',
            field=models.TextField(blank=True, null=True),
        ),
    ]
