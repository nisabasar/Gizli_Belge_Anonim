from django.contrib import admin
from .models import Domain, Reviewer, Submission, Log, Message

admin.site.register(Domain)
admin.site.register(Reviewer)
admin.site.register(Submission)
admin.site.register(Log)
admin.site.register(Message)
