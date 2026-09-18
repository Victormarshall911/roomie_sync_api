from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'university', 'gender', 'is_verified', 'is_admin', 'searching_for', 'created_at')
    list_filter = ('is_verified', 'is_admin', 'searching_for', 'gender')
    search_fields = ('full_name', 'university', 'department', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
