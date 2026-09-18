from rest_framework import serializers
from .models import Listing, ListingImage
from profiles.serializers import PublicProfileSerializer


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ('id', 'image', 'order', 'created_at')
        read_only_fields = ('id', 'created_at')


class ListingSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    user_profile = serializers.SerializerMethodField(read_only=True)
    match_percentage = serializers.SerializerMethodField(read_only=True)
    is_available = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = Listing
        fields = (
            'id',
            'user_id',
            'user_profile',
            'title',
            'description',
            'price',
            'location',
            'type',
            'searching_for',
            'is_available',
            'images',
            'uploaded_images',
            'created_at',
            'updated_at',
            'match_percentage',
        )
        read_only_fields = ('id', 'user_id', 'user_profile', 'images', 'created_at', 'updated_at', 'match_percentage')

    def get_user_profile(self, obj):
        profile = getattr(obj.user, 'profile', None)
        if profile:
            return PublicProfileSerializer(profile, context=self.context).data
        return None

    def get_match_percentage(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        current_profile = getattr(request.user, 'profile', None)
        target_profile = getattr(obj.user, 'profile', None)
        if not current_profile or not target_profile or current_profile.user_id == target_profile.user_id:
            return None
        try:
            from matching.services import calculate_match
            return calculate_match(current_profile, target_profile)
        except (ImportError, Exception):
            return None

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        listing = Listing.objects.create(**validated_data)
        for idx, img in enumerate(uploaded_images):
            ListingImage.objects.create(listing=listing, image=img, order=idx)
        return listing
