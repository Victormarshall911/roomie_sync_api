from django.urls import path
from .views import VerificationStatusView, VerificationSubmitView

urlpatterns = [
    path('status/', VerificationStatusView.as_view(), name='verification-status'),
    path('submit/', VerificationSubmitView.as_view(), name='verification-submit'),
]
