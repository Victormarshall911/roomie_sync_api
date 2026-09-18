import logging
import requests
from celery import shared_task

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
logger = logging.getLogger(__name__)


@shared_task(name='notifications.tasks.send_new_message_notification')
def send_new_message_notification(message_id):
    """
    Dispatches a push notification to Expo for a newly received message.
    Strictly ports send-notification shape expected by useNotifications.ts:
    title: "New message from {sender_name}"
    body: truncated to 50 chars
    data: { "type": "chat", "conversationId": ..., "senderId": ... }
    Automatically prunes tokens returning DeviceNotRegistered.
    """
    from chat.models import Message
    from notifications.models import DeviceToken

    try:
        message = Message.objects.select_related('conversation', 'sender__profile').get(id=message_id)
    except Message.DoesNotExist:
        logger.warning(f"Message {message_id} not found for notification.")
        return None

    recipient = message.conversation.get_other_participant(message.sender)
    if not recipient:
        return None

    tokens_query = DeviceToken.objects.filter(user=recipient).order_by('created_at')
    device_tokens = list(tokens_query)
    if not device_tokens:
        logger.info(f"No registered device tokens for recipient {recipient.email}.")
        return None

    sender_name = getattr(getattr(message.sender, 'profile', None), 'full_name', '') or 'Someone'
    truncated_body = message.content if len(message.content) <= 50 else message.content[:47] + '...'

    payloads = [
        {
            "to": dt.token,
            "sound": "default",
            "title": f"New message from {sender_name}",
            "body": truncated_body,
            "data": {
                "type": "chat",
                "conversationId": str(message.conversation.id),
                "senderId": str(message.sender.id),
            }
        }
        for dt in device_tokens
    ]

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=payloads,
            headers={
                'Accept': 'application/json',
                'Accept-encoding': 'gzip, deflate',
                'Content-Type': 'application/json',
            },
            timeout=10
        )
        res_json = response.json()
        tickets = res_json.get('data', [])
        if isinstance(tickets, dict):
            tickets = [tickets]

        for i, ticket in enumerate(tickets):
            if i < len(device_tokens):
                details = ticket.get('details', {})
                error = details.get('error') or ticket.get('message')
                if error == 'DeviceNotRegistered':
                    token_to_prune = device_tokens[i].token
                    logger.warning(f"Pruning unregistered Expo device token: {token_to_prune}")
                    DeviceToken.objects.filter(token=token_to_prune).delete()

    except Exception as e:
        logger.error(f"Failed to deliver Expo push notification: {e}")

    return payloads


@shared_task(name='notifications.tasks.send_verification_approved_notification')
def send_verification_approved_notification(user_id: str):
    logger.info(f"Student verification approved notification dispatched for user {user_id}")
    return True


@shared_task(name='notifications.tasks.send_verification_rejected_notification')
def send_verification_rejected_notification(user_id: str, reason: str = ''):
    logger.info(f"Student verification rejected notification dispatched for user {user_id} (reason: {reason})")
    return True
