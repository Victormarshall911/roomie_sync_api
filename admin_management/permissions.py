from rest_framework.permissions import BasePermission


class IsAdminProfileUser(BasePermission):
    """
    Permission class that grants access to users where is_staff is True
    OR profile.is_admin is True.
    Safely guards against missing profile without throwing ObjectDoesNotExist.
    """
    message = "Administrative privileges required to access this endpoint."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(user, 'is_staff', False):
            return True

        profile = getattr(user, 'profile', None)
        return bool(profile and getattr(profile, 'is_admin', False))
