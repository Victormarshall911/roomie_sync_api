from django.db.models.signals import post_save
from django.dispatch import receiver
from chat.models import Message
from .tasks import send_new_message_notification


@receiver(post_save, sender=Message)
def on_message_created_send_notification(sender, instance, created, **kwargs):
    if created:
        send_new_message_notification.delay(str(instance.id))
