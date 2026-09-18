import logging
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name='accounts.tasks.send_verification_email')
def send_verification_email(email: str, code: str):
    """
    Sends a 6-digit verification OTP code to the given email address.
    """
    subject = "Your RoomieSync Verification Code"
    message = (
        f"Hello,\n\n"
        f"Your 6-digit RoomieSync email verification code is: {code}\n"
        f"This code will expire in 15 minutes.\n\n"
        f"If you did not request this, please ignore this email.\n"
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@roomiesync.com')
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info(f"Verification email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")
        return False
