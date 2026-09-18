from django.urls import path
from .views import ProfileMeView, PublicProfileDetailView

urlpatterns = [
    path('me/', ProfileMeView.as_view(), name='profile-me'),
    path('<uuid:pk>/', PublicProfileDetailView.as_view(), name='profile-detail'),
]
