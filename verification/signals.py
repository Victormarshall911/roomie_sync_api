from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import VerificationRequest


@receiver(post_delete, sender=VerificationRequest)
def auto_delete_verification_document_on_delete(sender, instance, **kwargs):
    """
    Deletes the verification document file from storage when the request is deleted.
    """
    if instance.document:
        instance.document.delete(save=False)
