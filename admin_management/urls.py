from django.urls import path
from .views import (
    AdminVerificationListView,
    AdminVerificationApproveView,
    AdminVerificationRejectView,
    AdminVerificationDocumentView,
)

urlpatterns = [
    path('verifications/', AdminVerificationListView.as_view(), name='admin-verification-list'),
    path('verifications/<uuid:user_id>/approve/', AdminVerificationApproveView.as_view(), name='admin-verification-approve'),
    path('verifications/<uuid:user_id>/reject/', AdminVerificationRejectView.as_view(), name='admin-verification-reject'),
    path('verifications/<uuid:user_id>/document/', AdminVerificationDocumentView.as_view(), name='admin-verification-document'),
]
