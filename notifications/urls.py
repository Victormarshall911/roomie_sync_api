from django.urls import path
from .views import DeviceTokenCreateView, DeviceTokenDestroyView

urlpatterns = [
    path('devices/', DeviceTokenCreateView.as_view(), name='device-token-create'),
    path('devices/<str:token>/', DeviceTokenDestroyView.as_view(), name='device-token-destroy'),
]
