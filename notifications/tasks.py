import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='notifications.tasks.send_verification_approved_notification')
def send_verification_approved_notification(user_id: str):
    logger.info(f"Student verification approved notification dispatched for user {user_id}")
    return True


@shared_task(name='notifications.tasks.send_verification_rejected_notification')
def send_verification_rejected_notification(user_id: str, reason: str = ''):
    logger.info(f"Student verification rejected notification dispatched for user {user_id} (reason: {reason})")
    return True
