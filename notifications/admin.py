from django.contrib import admin
from .models import DeviceToken


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'platform', 'token', 'created_at', 'updated_at')
    list_filter = ('platform', 'created_at')
    search_fields = ('user__email', 'token')
