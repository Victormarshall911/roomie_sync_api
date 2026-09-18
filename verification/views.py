from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import VerificationRequest
from .serializers import VerificationRequestSerializer


class VerificationStatusView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        req = VerificationRequest.objects.filter(user=request.user).first()
        if not req:
            return Response({
                'status': 'unsubmitted',
                'is_verified': getattr(getattr(request.user, 'profile', None), 'is_verified', False),
            }, status=status.HTTP_200_OK)

        serializer = VerificationRequestSerializer(req, context={'request': request})
        data = serializer.data
        data['is_verified'] = getattr(getattr(request.user, 'profile', None), 'is_verified', False)
        return Response(data, status=status.HTTP_200_OK)


class VerificationSubmitView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = VerificationRequestSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            req = serializer.save()
            return Response(
                VerificationRequestSerializer(req, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
