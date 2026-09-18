import random
from django.core.cache import cache

OTP_EXPIRY_SECONDS = 900  # 15 minutes


def generate_otp() -> str:
    """Generate a random 6-digit numeric OTP code."""
    return f"{random.randint(100000, 999999)}"


def store_otp(email: str, code: str) -> None:
    """Store the 6-digit OTP code in Redis with a 15-minute TTL."""
    cache_key = f"email_otp:{email.strip().lower()}"
    cache.set(cache_key, str(code), timeout=OTP_EXPIRY_SECONDS)


def get_otp(email: str) -> str | None:
    """Retrieve the stored OTP code from Redis."""
    cache_key = f"email_otp:{email.strip().lower()}"
    return cache.get(cache_key)


def verify_otp(email: str, code: str) -> bool:
    """
    Verify the provided OTP against the stored code in Redis.
    If valid, remove the code from Redis and return True.
    """
    stored_code = get_otp(email)
    if stored_code is not None and str(stored_code).strip() == str(code).strip():
        cache_key = f"email_otp:{email.strip().lower()}"
        cache.delete(cache_key)
        return True
    return False
