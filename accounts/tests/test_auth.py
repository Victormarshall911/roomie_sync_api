import pytest
from unittest.mock import patch
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import User
from accounts.otp import get_otp, store_otp
from accounts.permissions import IsEmailVerified


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_user(db):
    return User.objects.create_user(
        email='testuser@example.com',
        password='StrongPassword123!',
        is_email_verified=False
    )


@pytest.mark.django_db
class TestAuthFlow:
    @patch('accounts.tasks.send_verification_email.delay')
    def test_register_creates_user_and_sends_otp(self, mock_email_task, api_client):
        url = reverse('auth-register')
        payload = {
            'email': 'newstudent@example.com',
            'password': 'Password123!',
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert 'tokens' in response.data
        assert 'access' in response.data['tokens']
        assert 'refresh' in response.data['tokens']

        # User is in DB with UUID PK and unverified email
        user = User.objects.get(email='newstudent@example.com')
        assert user.is_email_verified is False
        assert user.id is not None

        # Verify Celery task was called
        mock_email_task.assert_called_once()
        called_email, called_otp = mock_email_task.call_args[0]
        assert called_email == 'newstudent@example.com'
        assert len(called_otp) == 6

        # Verify OTP is stored in Redis cache
        stored_code = get_otp('newstudent@example.com')
        assert stored_code == called_otp

    def test_verify_email_with_invalid_code(self, api_client, sample_user):
        store_otp(sample_user.email, '123456')
        url = reverse('auth-verify-email')
        payload = {
            'email': sample_user.email,
            'code': '999999'  # Wrong code
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'code' in response.data

        sample_user.refresh_from_db()
        assert sample_user.is_email_verified is False

    def test_verify_email_with_valid_code(self, api_client, sample_user):
        store_otp(sample_user.email, '654321')
        url = reverse('auth-verify-email')
        payload = {
            'email': sample_user.email,
            'code': '654321'
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_email_verified'] is True

        sample_user.refresh_from_db()
        assert sample_user.is_email_verified is True

        # OTP should now be deleted from Redis
        assert get_otp(sample_user.email) is None

    @patch('accounts.tasks.send_verification_email.delay')
    def test_resend_code(self, mock_email_task, api_client, sample_user):
        url = reverse('auth-resend-code')
        payload = {'email': sample_user.email}
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_200_OK

        mock_email_task.assert_called_once()
        called_email, called_otp = mock_email_task.call_args[0]
        assert called_email == sample_user.email
        assert len(called_otp) == 6
        assert get_otp(sample_user.email) == called_otp

    def test_token_issuance_works_pre_and_post_verification(self, api_client, sample_user):
        url = reverse('auth-token-obtain-pair')
        login_payload = {
            'email': sample_user.email,
            'password': 'StrongPassword123!'
        }

        # 1. Pre-verification login: MUST SUCCEED (per confirmed decision)
        assert sample_user.is_email_verified is False
        response = api_client.post(url, login_payload, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['is_email_verified'] is False

        # 2. Post-verification login: MUST ALSO SUCCEED
        sample_user.is_email_verified = True
        sample_user.save()

        response = api_client.post(url, login_payload, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert response.data['user']['is_email_verified'] is True

    def test_token_refresh(self, api_client, sample_user):
        token_url = reverse('auth-token-obtain-pair')
        refresh_url = reverse('auth-token-refresh')

        login_res = api_client.post(token_url, {
            'email': sample_user.email,
            'password': 'StrongPassword123!'
        }, format='json')
        refresh_token = login_res.data['refresh']

        refresh_res = api_client.post(refresh_url, {'refresh': refresh_token}, format='json')
        assert refresh_res.status_code == status.HTTP_200_OK
        assert 'access' in refresh_res.data

    def test_logout_blacklists_refresh_token(self, api_client, sample_user):
        token_url = reverse('auth-token-obtain-pair')
        logout_url = reverse('auth-logout')
        refresh_url = reverse('auth-token-refresh')

        login_res = api_client.post(token_url, {
            'email': sample_user.email,
            'password': 'StrongPassword123!'
        }, format='json')
        access_token = login_res.data['access']
        refresh_token = login_res.data['refresh']

        # Logout with auth header
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_res = api_client.post(logout_url, {'refresh': refresh_token}, format='json')
        assert logout_res.status_code == status.HTTP_200_OK

        # Trying to refresh with the blacklisted token should fail
        api_client.credentials()
        attempt_res = api_client.post(refresh_url, {'refresh': refresh_token}, format='json')
        assert attempt_res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_me_account(self, api_client, sample_user):
        token_url = reverse('auth-token-obtain-pair')
        delete_url = reverse('auth-delete-account')

        login_res = api_client.post(token_url, {
            'email': sample_user.email,
            'password': 'StrongPassword123!'
        }, format='json')
        access_token = login_res.data['access']

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        delete_res = api_client.delete(delete_url)
        assert delete_res.status_code == status.HTTP_204_NO_CONTENT

        # Confirm user is completely deleted
        assert not User.objects.filter(id=sample_user.id).exists()

    def test_is_email_verified_permission_guard(self, api_client, sample_user):
        """
        Verify IsEmailVerified safely guards against missing profile and returns 403,
        never 500.
        """
        class DummyEmailGatedView(APIView):
            permission_classes = [IsEmailVerified]
            def get(self, request):
                return Response({'ok': True})

        view = DummyEmailGatedView.as_view()

        # 1. Unauthenticated request -> 401
        req = api_client.get('/dummy/').wsgi_request
        response = view(req)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        # 2. Authenticated but unverified user with NO profile -> 403
        sample_user.is_email_verified = False
        sample_user.save()
        api_client.force_authenticate(user=sample_user)
        req = api_client.get('/dummy/').wsgi_request
        req.user = sample_user
        response = view(req)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # 3. Authenticated verified user with NO profile -> 200, no ObjectDoesNotExist
        sample_user.is_email_verified = True
        sample_user.save()
        req.user = sample_user
        response = view(req)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'ok': True}
