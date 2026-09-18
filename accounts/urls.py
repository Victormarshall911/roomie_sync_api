from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    VerifyEmailView,
    ResendCodeView,
    CustomTokenObtainPairView,
    LogoutView,
    DeleteAccountView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('verify-email/', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('resend-code/', ResendCodeView.as_view(), name='auth-resend-code'),
    path('token/', CustomTokenObtainPairView.as_view(), name='auth-token-obtain-pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', DeleteAccountView.as_view(), name='auth-delete-account'),
]
