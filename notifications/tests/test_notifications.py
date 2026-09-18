import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from chat.models import Conversation, Message
from notifications.models import DeviceToken
from notifications.tasks import send_new_message_notification


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sender_user(db):
    user = User.objects.create_user(email='sender@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Tunde Sender'})
    user.profile = p
    return user


@pytest.fixture
def recipient_user(db):
    user = User.objects.create_user(email='recipient@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Bisi Recipient'})
    user.profile = p
    return user


@pytest.fixture
def chat_convo(db, sender_user, recipient_user):
    u1, u2 = (sender_user, recipient_user) if str(sender_user.id) < str(recipient_user.id) else (recipient_user, sender_user)
    return Conversation.objects.create(user1=u1, user2=u2)


@pytest.mark.django_db
class TestNotifications:
    @patch('notifications.tasks.send_new_message_notification.delay')
    def test_message_creation_triggers_celery_signal(self, mock_delay, chat_convo, sender_user):
        # Creating a message should trigger the post_save signal
        msg = Message.objects.create(
            conversation=chat_convo,
            sender=sender_user,
            content='Test notification message'
        )
        mock_delay.assert_called_once_with(str(msg.id))

    @patch('requests.post')
    def test_notification_payload_shape_and_multi_device(self, mock_post, chat_convo, sender_user, recipient_user):
        # 1. Register two device tokens for recipient (multi-device)
        dt_ios = DeviceToken.objects.create(
            user=recipient_user,
            token='ExponentPushToken[recipient-ios-device-123]',
            platform='ios'
        )
        dt_android = DeviceToken.objects.create(
            user=recipient_user,
            token='ExponentPushToken[recipient-android-device-456]',
            platform='android'
        )

        # Mock successful Expo response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': [
                {'status': 'ok', 'id': 'ticket-1'},
                {'status': 'ok', 'id': 'ticket-2'}
            ]
        }
        mock_post.return_value = mock_response

        # Long message content exceeding 50 chars to test exact truncation
        long_content = "Hello! I saw your room listing and I would really love to schedule a visit tomorrow."
        msg = Message.objects.create(
            conversation=chat_convo,
            sender=sender_user,
            content=long_content
        )

        payloads = send_new_message_notification(msg.id)
        assert payloads is not None
        assert len(payloads) == 2  # Sent to both devices

        # Verify exact payload shape matching send-notification and useNotifications.ts
        payload_1 = payloads[0]
        assert payload_1['to'] == dt_ios.token
        assert payload_1['sound'] == 'default'
        assert payload_1['title'] == 'New message from Tunde Sender'
        assert len(payload_1['body']) == 50
        assert payload_1['body'] == long_content[:47] + '...'
        assert payload_1['data'] == {
            'type': 'chat',
            'conversationId': str(chat_convo.id),
            'senderId': str(sender_user.id)
        }

        payload_2 = payloads[1]
        assert payload_2['to'] == dt_android.token

        # Verify requests.post was called with EXPO_PUSH_URL and correct JSON
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://exp.host/--/api/v2/push/send"
        assert kwargs['json'] == payloads

    def test_recipient_with_zero_tokens_does_not_error(self, chat_convo, sender_user, recipient_user):
        # Ensure recipient has 0 device tokens
        DeviceToken.objects.filter(user=recipient_user).delete()

        msg = Message.objects.create(
            conversation=chat_convo,
            sender=sender_user,
            content='Message to user with no devices'
        )
        result = send_new_message_notification(msg.id)
        assert result is None  # Handled cleanly without exception

    @patch('requests.post')
    def test_prunes_device_not_registered_tokens(self, mock_post, chat_convo, sender_user, recipient_user):
        dt_active = DeviceToken.objects.create(
            user=recipient_user,
            token='ExponentPushToken[active-token]',
            platform='ios'
        )
        dt_stale = DeviceToken.objects.create(
            user=recipient_user,
            token='ExponentPushToken[stale-token-to-prune]',
            platform='android'
        )

        # Mock Expo response where stale token returns DeviceNotRegistered
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': [
                {'status': 'ok', 'id': 'ticket-ok'},
                {'status': 'error', 'message': 'DeviceNotRegistered', 'details': {'error': 'DeviceNotRegistered'}}
            ]
        }
        mock_post.return_value = mock_response

        msg = Message.objects.create(
            conversation=chat_convo,
            sender=sender_user,
            content='Testing token pruning'
        )

        send_new_message_notification(msg.id)

        # Verify active token remains, while stale token was automatically deleted from DB
        assert DeviceToken.objects.filter(token=dt_active.token).exists()
        assert not DeviceToken.objects.filter(token=dt_stale.token).exists()

    def test_device_token_register_and_deregister_endpoints(self, api_client, recipient_user):
        api_client.force_authenticate(user=recipient_user)

        register_url = reverse('device-token-create')
        token_str = 'ExponentPushToken[unique-push-token-789]'

        # 1. Register device token
        res_reg = api_client.post(register_url, {'token': token_str, 'platform': 'ios'}, format='json')
        assert res_reg.status_code == status.HTTP_201_CREATED
        assert DeviceToken.objects.filter(user=recipient_user, token=token_str).exists()

        # 2. Deregister device token on logout
        destroy_url = reverse('device-token-destroy', kwargs={'token': token_str})
        res_del = api_client.delete(destroy_url)
        assert res_del.status_code == status.HTTP_204_NO_CONTENT
        assert not DeviceToken.objects.filter(token=token_str).exists()
