from django.contrib import admin
from .models import Submission, Log

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'status', 'timestamp')
    search_fields = ('tracking_number',)

@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ('submission', 'action', 'timestamp')
    search_fields = ('submission__tracking_number', 'action')
