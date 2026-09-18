from rest_framework.permissions import BasePermission


class IsEmailVerified(BasePermission):
    """
    Allows access only to authenticated users whose email address is verified.
    Guards against missing profile or unauthenticated user safely.
    """
    message = "Email address must be verified to perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(getattr(user, 'is_email_verified', False))
