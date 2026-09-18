import uuid
from django.db import models
from django.conf import settings


class Listing(models.Model):
    TYPE_CHOICES = (
        ('Room', 'Room'),
        ('Roommate', 'Roommate'),
    )

    SEARCHING_FOR_CHOICES = (
        ('Looking for Roommate', 'Looking for Roommate'),
        ('Listing a Space', 'Listing a Space'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listings'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    price = models.PositiveIntegerField()
    location = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    searching_for = models.CharField(max_length=50, choices=SEARCHING_FOR_CHOICES)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'listings'
        verbose_name = 'Listing'
        verbose_name_plural = 'Listings'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.location} (₦{self.price:,})"


class ListingImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='listings/%Y/%m/')
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'listing_images'
        ordering = ['order', 'created_at']
        verbose_name = 'Listing Image'
        verbose_name_plural = 'Listing Images'

    def __str__(self):
        return f"Image for {self.listing.title} (#{self.order})"
