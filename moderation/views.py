from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Report, Block
from .serializers import ReportSerializer, BlockSerializer


class ReportListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ReportSerializer

    def get_queryset(self):
        user = self.request.user
        is_admin = bool(user.is_staff or getattr(getattr(user, 'profile', None), 'is_admin', False))
        if is_admin:
            return Report.objects.select_related('reporter', 'reported_user', 'listing').all()
        # Regular users only see their own filed reports
        return Report.objects.filter(reporter=user).select_related('reporter', 'reported_user', 'listing')


class BlockListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = BlockSerializer

    def get_queryset(self):
        return Block.objects.filter(blocker=self.request.user).select_related('blocker', 'blocked__profile')


class BlockDestroyView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def delete(self, request, blocked_id):
        deleted_count, _ = Block.objects.filter(blocker=request.user, blocked_id=blocked_id).delete()
        if deleted_count > 0:
            return Response({'message': 'User unblocked successfully.'}, status=status.HTTP_204_NO_CONTENT)
        return Response({'detail': 'Block record not found.'}, status=status.HTTP_404_NOT_FOUND)
