import os
from rest_framework import serializers
from .models import VerificationRequest

ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'application/pdf'}
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


class VerificationRequestSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = VerificationRequest
        fields = (
            'id',
            'user_id',
            'user_email',
            'user_full_name',
            'document',
            'status',
            'rejection_reason',
            'submitted_at',
            'reviewed_at',
        )
        read_only_fields = ('id', 'user_id', 'user_email', 'user_full_name', 'status', 'rejection_reason', 'submitted_at', 'reviewed_at')

    def get_user_full_name(self, obj):
        profile = getattr(obj.user, 'profile', None)
        return getattr(profile, 'full_name', '')

    def validate_document(self, value):
        # 1. Validate file size (5MB limit)
        if value.size > MAX_FILE_SIZE:
            raise serializers.ValidationError(f"File size exceeds 5MB limit. Current size is {value.size / (1024 * 1024):.2f}MB.")

        # 2. Validate file extension
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(f"Unsupported file extension '{ext}'. Allowed extensions: .jpg, .jpeg, .png, .pdf.")

        # 3. Validate content type
        content_type = getattr(value, 'content_type', '')
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            raise serializers.ValidationError(f"Unsupported MIME type '{content_type}'. Allowed types: image/jpeg, image/png, application/pdf.")

        return value

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        user = request.user
        existing = VerificationRequest.objects.filter(user=user).first()
        if existing:
            if existing.status == 'approved':
                raise serializers.ValidationError("Your student verification is already approved.")
            elif existing.status == 'pending':
                raise serializers.ValidationError("You already have a pending verification request under review.")

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        document = validated_data['document']

        # If previous request was rejected, update and reset to pending
        existing = VerificationRequest.objects.filter(user=user).first()
        if existing and existing.status == 'rejected':
            existing.document = document
            existing.status = 'pending'
            existing.rejection_reason = ''
            existing.reviewed_at = None
            existing.reviewed_by = None
            existing.save()
            return existing

        validated_data['user'] = user
        return super().create(validated_data)
