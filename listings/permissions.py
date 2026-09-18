from rest_framework.permissions import BasePermission


class IsVerifiedStudent(BasePermission):
    """
    Allows access only to authenticated users whose profile has is_verified=True.
    Safely guards against missing profile without raising exceptions.
    """
    message = "Only verified students can create listings. Please upload your student ID."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        profile = getattr(user, 'profile', None)
        return bool(profile and getattr(profile, 'is_verified', False))


class IsOwner(BasePermission):
    """
    Object-level permission to only allow owners of a listing to edit or delete it.
    """
    message = "You must be the owner of this listing to perform this action."

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user
