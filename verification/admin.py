from django.contrib import admin
from .models import VerificationRequest


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'submitted_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'submitted_at')
    search_fields = ('user__email', 'user__profile__full_name')
