from django.contrib import admin
from .models import Report, Block


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'reported_user', 'listing', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reporter__email', 'reported_user__email', 'reason')


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ('id', 'blocker', 'blocked', 'created_at')
    search_fields = ('blocker__email', 'blocked__email')
