import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_user1'
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_user2'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'conversations'
        constraints = [
            models.UniqueConstraint(fields=['user1', 'user2'], name='unique_conversation_participants')
        ]
        ordering = ['-created_at']

    def clean(self):
        if self.user1_id and self.user2_id and self.user1_id == self.user2_id:
            raise ValidationError("Cannot create a conversation with oneself.")

    def save(self, *args, **kwargs):
        # Enforce canonical ordering min(u1, u2), max(u1, u2)
        if self.user1_id and self.user2_id:
            u1_str = str(self.user1_id)
            u2_str = str(self.user2_id)
            if u1_str > u2_str:
                self.user1, self.user2 = self.user2, self.user1

        self.full_clean()
        super().save(*args, **kwargs)

    def get_other_participant(self, user):
        if user.id == self.user1_id:
            return self.user2
        elif user.id == self.user2_id:
            return self.user1
        return None

    def __str__(self):
        return f"Conversation between {self.user1.email} and {self.user2.email}"


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender.email} at {self.created_at}"
