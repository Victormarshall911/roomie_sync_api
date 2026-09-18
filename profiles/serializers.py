from rest_framework import serializers
from .models import Profile


class ProfileMeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Profile
        fields = (
            'id',
            'email',
            'full_name',
            'university',
            'department',
            'gender',
            'budget_min',
            'budget_max',
            'location_preference',
            'sleep_habit',
            'cleanliness',
            'socializing',
            'smoking',
            'noise_level',
            'study_time',
            'drinking_habit',
            'pets_preference',
            'avatar',
            'is_verified',
            'is_admin',
            'searching_for',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'email', 'is_verified', 'is_admin', 'created_at', 'updated_at')


class PublicProfileSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='user.id', read_only=True)
    match_percentage = serializers.SerializerMethodField(required=False)

    class Meta:
        model = Profile
        fields = (
            'id',
            'full_name',
            'university',
            'department',
            'gender',
            'budget_min',
            'budget_max',
            'location_preference',
            'sleep_habit',
            'cleanliness',
            'socializing',
            'smoking',
            'noise_level',
            'study_time',
            'drinking_habit',
            'pets_preference',
            'avatar',
            'is_verified',
            'searching_for',
            'created_at',
            'match_percentage',
        )
        read_only_fields = fields

    def get_match_percentage(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        current_profile = getattr(request.user, 'profile', None)
        if not current_profile or current_profile.user_id == obj.user_id:
            return None
        try:
            from matching.services import calculate_match
            return calculate_match(current_profile, obj)
        except (ImportError, Exception):
            return None
