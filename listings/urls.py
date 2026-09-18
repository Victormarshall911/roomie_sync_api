from django.urls import path
from .views import ListingListCreateView, ListingDetailView, ToggleAvailabilityView

urlpatterns = [
    path('', ListingListCreateView.as_view(), name='listing-list-create'),
    path('<uuid:pk>/', ListingDetailView.as_view(), name='listing-detail'),
    path('<uuid:pk>/toggle-availability/', ToggleAvailabilityView.as_view(), name='listing-toggle-availability'),
]
