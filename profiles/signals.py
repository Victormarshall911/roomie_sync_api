from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile_fallback(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={
                'full_name': instance.email.split('@')[0],
            }
        )


@receiver(pre_save, sender=Profile)
def auto_delete_old_avatar_on_change(sender, instance, **kwargs):
    """
    Deletes the previous avatar file from storage when a new avatar is uploaded.
    Prevents storage leaks and orphan images.
    """
    if not instance.pk:
        return
    try:
        old_profile = Profile.objects.get(pk=instance.pk)
    except Profile.DoesNotExist:
        return

    if old_profile.avatar and old_profile.avatar != instance.avatar:
        old_profile.avatar.delete(save=False)


@receiver(post_delete, sender=Profile)
def auto_delete_avatar_on_profile_delete(sender, instance, **kwargs):
    """
    Deletes the avatar file from storage when the profile is deleted.
    """
    if instance.avatar:
        instance.avatar.delete(save=False)
