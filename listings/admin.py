from django.contrib import admin
from .models import Listing, ListingImage


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 1


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'price', 'location', 'type', 'searching_for', 'is_available', 'created_at')
    list_filter = ('type', 'searching_for', 'is_available', 'created_at')
    search_fields = ('title', 'location', 'description', 'user__email')
    inlines = [ListingImageInline]
