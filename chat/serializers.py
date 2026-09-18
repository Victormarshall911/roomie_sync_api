from rest_framework import serializers
from accounts.models import User
from profiles.serializers import PublicProfileSerializer
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.UUIDField(source='sender.id', read_only=True)
    sender_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Message
        fields = ('id', 'conversation', 'sender_id', 'sender_name', 'content', 'is_read', 'created_at')
        read_only_fields = ('id', 'conversation', 'sender_id', 'sender_name', 'is_read', 'created_at')

    def get_sender_name(self, obj):
        profile = getattr(obj.sender, 'profile', None)
        return getattr(profile, 'full_name', '') or obj.sender.email


class ConversationListSerializer(serializers.ModelSerializer):
    partner = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ('id', 'partner', 'last_message', 'unread_count', 'created_at')

    def get_partner(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        other_user = obj.get_other_participant(request.user)
        if not other_user:
            return None
        profile = getattr(other_user, 'profile', None)
        if profile:
            return PublicProfileSerializer(profile, context=self.context).data
        return {
            'id': str(other_user.id),
            'full_name': other_user.email,
        }

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if not last_msg:
            return None
        return {
            'id': str(last_msg.id),
            'content': last_msg.content,
            'sender_id': str(last_msg.sender_id),
            'is_read': last_msg.is_read,
            'created_at': last_msg.created_at,
        }

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request:
            return 0
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()


class StartConversationSerializer(serializers.Serializer):
    recipient_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    def validate_recipient_id(self, value):
        request = self.context.get('request')
        if request and request.user == value:
            raise serializers.ValidationError("Cannot start a conversation with yourself.")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        recipient = validated_data['recipient_id']

        u1, u2 = (user, recipient) if str(user.id) < str(recipient.id) else (recipient, user)
        conversation, _ = Conversation.objects.get_or_create(user1=u1, user2=u2)
        return conversation
