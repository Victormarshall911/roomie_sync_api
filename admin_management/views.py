import os
import time
from django.utils import timezone
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.http import FileResponse, Http404
from django.conf import settings
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import User
from profiles.models import Profile
from verification.models import VerificationRequest
from verification.serializers import VerificationRequestSerializer
from .permissions import IsAdminProfileUser

DOCUMENT_SIGNED_URL_EXPIRY_SECONDS = 1800  # 30 minutes (Fixing original 60s bug)


def generate_signed_document_url(verification_req, request=None, expires_in=DOCUMENT_SIGNED_URL_EXPIRY_SECONDS):
    """
    Generates a secure, time-limited signed URL for admin document viewing.
    Guarantees expiration is between 1800s (30m) and 3600s (60m).
    """
    signer = TimestampSigner()
    token = signer.sign(str(verification_req.id))

    if settings.AWS_ACCESS_KEY_ID and settings.AWS_STORAGE_BUCKET_NAME:
        import boto3
        client_kwargs = {
            'service_name': 's3',
            'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
            'region_name': getattr(settings, 'AWS_S3_REGION_NAME', 'auto'),
        }
        endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url

        s3_client = boto3.client(**client_kwargs)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': verification_req.document.name,
            },
            ExpiresIn=expires_in
        )
        return url, expires_in
    else:
        # Dev local storage signed URL
        base_url = f"/api/v1/admin/verifications/{verification_req.user_id}/document/?token={token}"
        if request:
            base_url = request.build_absolute_uri(base_url)
        return base_url, expires_in


class AdminVerificationListView(generics.ListAPIView):
    permission_classes = (IsAdminProfileUser,)
    serializer_class = VerificationRequestSerializer

    def get_queryset(self):
        return VerificationRequest.objects.filter(status='pending').select_related('user__profile').order_by('-submitted_at')


class AdminVerificationApproveView(APIView):
    permission_classes = (IsAdminProfileUser,)

    def post(self, request, user_id):
        try:
            verif = VerificationRequest.objects.select_related('user__profile').get(user_id=user_id)
        except VerificationRequest.DoesNotExist:
            return Response({'detail': 'Verification request not found.'}, status=status.HTTP_404_NOT_FOUND)

        verif.status = 'approved'
        verif.reviewed_by = request.user
        verif.reviewed_at = timezone.now()
        verif.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        # Update profile is_verified
        profile = getattr(verif.user, 'profile', None)
        if profile:
            profile.is_verified = True
            profile.save(update_fields=['is_verified'])

        # Trigger notification task
        try:
            from notifications.tasks import send_verification_approved_notification
            send_verification_approved_notification.delay(str(verif.user_id))
        except Exception:
            pass

        return Response({
            'message': 'Student verification approved successfully.',
            'status': 'approved',
            'is_verified': True
        }, status=status.HTTP_200_OK)


class AdminVerificationRejectView(APIView):
    permission_classes = (IsAdminProfileUser,)

    def post(self, request, user_id):
        try:
            verif = VerificationRequest.objects.select_related('user__profile').get(user_id=user_id)
        except VerificationRequest.DoesNotExist:
            return Response({'detail': 'Verification request not found.'}, status=status.HTTP_404_NOT_FOUND)

        reason = request.data.get('reason', '').strip()
        verif.status = 'rejected'
        verif.rejection_reason = reason
        verif.reviewed_by = request.user
        verif.reviewed_at = timezone.now()
        verif.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])

        profile = getattr(verif.user, 'profile', None)
        if profile:
            profile.is_verified = False
            profile.save(update_fields=['is_verified'])

        # Trigger notification task
        try:
            from notifications.tasks import send_verification_rejected_notification
            send_verification_rejected_notification.delay(str(verif.user_id), reason)
        except Exception:
            pass

        return Response({
            'message': 'Student verification rejected.',
            'status': 'rejected',
            'rejection_reason': reason,
            'is_verified': False
        }, status=status.HTTP_200_OK)


class AdminVerificationDocumentView(APIView):
    permission_classes = (permissions.AllowAny,)  # Governed by signed token or admin session

    def get(self, request, user_id):
        token = request.query_params.get('token')

        # Allow if authenticated admin OR valid signed token
        is_admin = bool(
            request.user.is_authenticated and
            (request.user.is_staff or getattr(getattr(request.user, 'profile', None), 'is_admin', False))
        )

        try:
            verif = VerificationRequest.objects.get(user_id=user_id)
        except VerificationRequest.DoesNotExist:
            return Response({'detail': 'Verification request not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            if not token:
                return Response({'detail': 'Authentication or valid token required.'}, status=status.HTTP_403_FORBIDDEN)
            signer = TimestampSigner()
            try:
                original_id = signer.unsign(token, max_age=DOCUMENT_SIGNED_URL_EXPIRY_SECONDS)
                if original_id != str(verif.id):
                    return Response({'detail': 'Invalid token for this document.'}, status=status.HTTP_403_FORBIDDEN)
            except SignatureExpired:
                return Response({'detail': 'Signed document URL has expired.'}, status=status.HTTP_403_FORBIDDEN)
            except BadSignature:
                return Response({'detail': 'Invalid document signature.'}, status=status.HTTP_403_FORBIDDEN)

        # If requesting JSON info or if called as admin without token to get URL
        if request.query_params.get('format') == 'json' or not token:
            url, expires_in = generate_signed_document_url(
                verif,
                request=request,
                expires_in=DOCUMENT_SIGNED_URL_EXPIRY_SECONDS
            )
            return Response({
                'document_url': url,
                'expires_in': expires_in,
                'status': verif.status,
            }, status=status.HTTP_200_OK)

        # Stream the document
        if not verif.document:
            return Response({'detail': 'No document file attached.'}, status=status.HTTP_404_NOT_FOUND)

        return FileResponse(verif.document.open('rb'))
