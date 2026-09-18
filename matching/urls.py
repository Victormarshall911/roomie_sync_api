from django.urls import path
from .views import RoommateMatchesView

urlpatterns = [
    path('', RoommateMatchesView.as_view(), name='matches-list'),
]
