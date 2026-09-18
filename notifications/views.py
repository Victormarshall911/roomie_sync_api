from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import DeviceToken
from .serializers import DeviceTokenSerializer


class DeviceTokenCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            device_token = serializer.save()
            return Response(DeviceTokenSerializer(device_token).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeviceTokenDestroyView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def delete(self, request, token):
        deleted_count, _ = DeviceToken.objects.filter(user=request.user, token=token).delete()
        if deleted_count > 0:
            return Response({'message': 'Device token deregistered.'}, status=status.HTTP_204_NO_CONTENT)
        return Response({'detail': 'Token not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
