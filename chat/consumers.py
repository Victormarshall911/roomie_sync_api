import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Conversation, Message


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']

        # Verify conversation existence and user membership
        is_member = await self._check_membership(self.conversation_id, self.user.id)
        if not is_member:
            await self.close(code=4003)
            return

        self.chat_group_name = f"chat_{self.conversation_id}"
        self.user_group_name = f"user_{self.user.id}"

        # Join chat room group
        await self.channel_layer.group_add(
            self.chat_group_name,
            self.channel_name
        )

        # Join personal user notification group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'chat_group_name'):
            await self.channel_layer.group_discard(
                self.chat_group_name,
                self.channel_name
            )
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        message_text = content.get('content', '').strip()
        if not message_text:
            return

        # Save message in DB
        msg_data = await self._save_message(self.conversation_id, self.user, message_text)
        if not msg_data:
            return

        # Broadcast to conversation group
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'chat_message',
                'message': msg_data
            }
        )

        # Broadcast unread badge update to recipient's personal user group
        recipient_id = msg_data.get('recipient_id')
        if recipient_id:
            await self.channel_layer.group_send(
                f"user_{recipient_id}",
                {
                    'type': 'unread_badge_update',
                    'data': {
                        'type': 'new_message',
                        'conversation_id': str(self.conversation_id),
                        'message_id': msg_data['id']
                    }
                }
            )

    async def chat_message(self, event):
        await self.send_json({
            'type': 'new_message',
            'message': event['message']
        })

    async def unread_badge_update(self, event):
        await self.send_json({
            'type': 'unread_badge_update',
            'data': event['data']
        })

    @database_sync_to_async
    def _check_membership(self, conversation_id, user_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            return user_id in (conversation.user1_id, conversation.user2_id)
        except (Conversation.DoesNotExist, Exception):
            return False

    @database_sync_to_async
    def _save_message(self, conversation_id, sender, content):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            recipient = conversation.get_other_participant(sender)
            message = Message.objects.create(
                conversation=conversation,
                sender=sender,
                content=content
            )
            sender_profile = getattr(sender, 'profile', None)
            sender_name = getattr(sender_profile, 'full_name', '') or sender.email

            return {
                'id': str(message.id),
                'conversation_id': str(conversation.id),
                'sender_id': str(sender.id),
                'sender_name': sender_name,
                'recipient_id': str(recipient.id) if recipient else None,
                'content': message.content,
                'is_read': message.is_read,
                'created_at': message.created_at.isoformat(),
            }
        except Exception:
            return None
