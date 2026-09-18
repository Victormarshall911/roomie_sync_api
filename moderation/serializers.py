from rest_framework import serializers
from accounts.models import User
from listings.models import Listing
from .models import Report, Block


class ReportSerializer(serializers.ModelSerializer):
    reporter_id = serializers.UUIDField(source='reporter.id', read_only=True)
    reported_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='reported_user',
        write_only=True
    )
    reported_user = serializers.SerializerMethodField(read_only=True)
    listing_id = serializers.PrimaryKeyRelatedField(
        queryset=Listing.objects.all(),
        source='listing',
        required=False,
        allow_null=True
    )

    class Meta:
        model = Report
        fields = (
            'id',
            'reporter_id',
            'reported_user_id',
            'reported_user',
            'listing_id',
            'reason',
            'status',
            'created_at',
        )
        read_only_fields = ('id', 'reporter_id', 'status', 'created_at')

    def get_reported_user(self, obj):
        return {
            'id': str(obj.reported_user.id),
            'email': obj.reported_user.email,
        }

    def validate(self, attrs):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            reported_user = attrs.get('reported_user')
            if reported_user and reported_user == request.user:
                raise serializers.ValidationError({"reported_user_id": "You cannot report yourself."})
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['reporter'] = request.user
        return super().create(validated_data)


class BlockSerializer(serializers.ModelSerializer):
    blocker_id = serializers.UUIDField(source='blocker.id', read_only=True)
    blocked_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='blocked',
        write_only=True
    )
    blocked_user = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Block
        fields = ('id', 'blocker_id', 'blocked_id', 'blocked_user', 'created_at')
        read_only_fields = ('id', 'blocker_id', 'created_at')

    def get_blocked_user(self, obj):
        return {
            'id': str(obj.blocked.id),
            'email': obj.blocked.email,
            'full_name': getattr(getattr(obj.blocked, 'profile', None), 'full_name', '')
        }

    def validate(self, attrs):
        request = self.context.get('request')
        blocked_user = attrs.get('blocked')
        if request and request.user == blocked_user:
            raise serializers.ValidationError({"blocked_id": "You cannot block yourself."})

        if request and Block.objects.filter(blocker=request.user, blocked=blocked_user).exists():
            raise serializers.ValidationError({"blocked_id": "You have already blocked this user."})

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['blocker'] = request.user
        return super().create(validated_data)
