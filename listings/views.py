from rest_framework import generics, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Listing
from .serializers import ListingSerializer
from .filters import ListingFilter
from .permissions import IsVerifiedStudent, IsOwner


class ListingListCreateView(generics.ListCreateAPIView):
    serializer_class = ListingSerializer
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = ListingFilter
    search_fields = ('title', 'location', 'description', 'user__profile__full_name', 'user__email')
    ordering_fields = ('created_at', 'price')
    ordering = ('-created_at',)

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsVerifiedStudent()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        qs = Listing.objects.select_related('user__profile').prefetch_related('images').all()
        user = self.request.user
        if user and user.is_authenticated:
            try:
                from moderation.models import Block
                blocked_ids = Block.objects.filter(blocker=user).values_list('blocked_id', flat=True)
                blocking_ids = Block.objects.filter(blocked=user).values_list('blocker_id', flat=True)
                qs = qs.exclude(user_id__in=blocked_ids).exclude(user_id__in=blocking_ids)
            except Exception:
                pass
        return qs


class ListingDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Listing.objects.select_related('user__profile').prefetch_related('images').all()
    serializer_class = ListingSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [permissions.IsAuthenticated(), IsOwner()]
        return [permissions.AllowAny()]


class ToggleAvailabilityView(APIView):
    permission_classes = (permissions.IsAuthenticated, IsOwner)

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk)
        except Listing.DoesNotExist:
            return Response({'detail': 'Listing not found.'}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, listing)
        listing.is_available = not listing.is_available
        listing.save(update_fields=['is_available'])
        serializer = ListingSerializer(listing, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
