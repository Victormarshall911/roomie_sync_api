from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import ListingImage


@receiver(post_delete, sender=ListingImage)
def auto_delete_listing_image_on_delete(sender, instance, **kwargs):
    """
    Deletes the listing image file from storage when the record is deleted.
    """
    if instance.image:
        instance.image.delete(save=False)
