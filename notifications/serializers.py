from rest_framework import serializers
from .models import DeviceToken


class DeviceTokenSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source='user.id', read_only=True)

    class Meta:
        model = DeviceToken
        fields = ('id', 'user_id', 'token', 'platform', 'created_at', 'updated_at')
        read_only_fields = ('id', 'user_id', 'created_at', 'updated_at')

    def create(self, validated_data):
        request = self.context.get('request')
        token = validated_data['token']
        platform = validated_data.get('platform', 'ios')

        device_token, _ = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'platform': platform
            }
        )
        return device_token
