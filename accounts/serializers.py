from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.db import transaction
from .models import User
from .otp import generate_otp, store_otp, verify_otp
from .tasks import send_verification_email


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    profile = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'is_email_verified', 'created_at', 'profile')
        read_only_fields = ('id', 'is_email_verified', 'created_at')

    def create(self, validated_data):
        profile_data = validated_data.pop('profile', None)
        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            if profile_data:
                from profiles.models import Profile
                Profile.objects.update_or_create(user=user, defaults=profile_data)

            # Generate OTP, store in Redis, dispatch Celery task
            otp_code = generate_otp()
            store_otp(user.email, otp_code)
            send_verification_email.delay(user.email, otp_code)

        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        email = attrs.get('email').strip().lower()
        code = attrs.get('code').strip()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist."})

        if not verify_otp(email, code):
            raise serializers.ValidationError({"code": "Invalid or expired verification code."})

        attrs['user'] = user
        return attrs


class ResendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.strip().lower()
        if not User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return email


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        self.token = attrs.get('refresh')
        return attrs

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.token)
            token.blacklist()
        except TokenError:
            raise serializers.ValidationError({"refresh": "Invalid or expired refresh token."})


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['is_email_verified'] = user.is_email_verified
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'is_email_verified': self.user.is_email_verified,
        }
        return data
