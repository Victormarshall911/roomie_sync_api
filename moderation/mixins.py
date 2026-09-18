from .models import Block


class BlockedUsersFilterMixin:
    """
    Reusable mixin that filters out items associated with users blocked by
    or blocking the current authenticated user.
    """
    user_field_name = 'user'

    def filter_blocked_users(self, queryset):
        request = getattr(self, 'request', None)
        if not request or not request.user or not request.user.is_authenticated:
            return queryset

        user = request.user
        blocked_ids = Block.objects.filter(blocker=user).values_list('blocked_id', flat=True)
        blocking_ids = Block.objects.filter(blocked=user).values_list('blocker_id', flat=True)

        excluded_ids = set(blocked_ids).union(set(blocking_ids))
        if not excluded_ids:
            return queryset

        filter_kwargs = {f"{self.user_field_name}__in": excluded_ids}
        return queryset.exclude(**filter_kwargs)
