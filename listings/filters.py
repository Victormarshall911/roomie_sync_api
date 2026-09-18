import django_filters
from .models import Listing


class ListingFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    location = django_filters.CharFilter(field_name='location', lookup_expr='icontains')
    searching_for = django_filters.CharFilter(field_name='searching_for', lookup_expr='exact')
    type = django_filters.CharFilter(field_name='type', lookup_expr='exact')
    is_available = django_filters.BooleanFilter(field_name='is_available')

    class Meta:
        model = Listing
        fields = ['searching_for', 'type', 'location', 'min_price', 'max_price', 'is_available']
