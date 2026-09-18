from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from profiles.models import Profile
from profiles.serializers import PublicProfileSerializer
from .services import calculate_match


class RoommateMatchesView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        current_profile = getattr(request.user, 'profile', None)
        if not current_profile:
            return Response({'detail': 'User profile does not exist.'}, status=status.HTTP_400_BAD_REQUEST)

        # Exclude self
        queryset = Profile.objects.exclude(user=request.user)

        # Exclude blocked users if moderation exists
        try:
            from moderation.models import Block
            blocked_ids = Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
            blocking_ids = Block.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
            queryset = queryset.exclude(user_id__in=blocked_ids).exclude(user_id__in=blocking_ids)
        except Exception:
            pass

        # Optional filter by searching_for
        searching_for = request.query_params.get('searching_for')
        if searching_for:
            queryset = queryset.filter(searching_for=searching_for)

        profiles_list = list(queryset)

        # Compute match percentage and sort
        matches = []
        for target_profile in profiles_list:
            match_pct = calculate_match(current_profile, target_profile)
            matches.append((target_profile, match_pct))

        matches.sort(key=lambda x: x[1], reverse=True)

        results = []
        for profile_obj, match_pct in matches:
            data = PublicProfileSerializer(profile_obj, context={'request': request}).data
            data['match_percentage'] = match_pct
            results.append(data)

        return Response(results, status=status.HTTP_200_OK)
