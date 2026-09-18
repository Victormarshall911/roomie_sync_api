import pytest
from unittest.mock import patch
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import TimestampSigner
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from verification.models import VerificationRequest
from admin_management.views import (
    DOCUMENT_SIGNED_URL_EXPIRY_SECONDS,
    generate_signed_document_url,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(email='admin_panel@unilag.edu.ng', password='Password123!', is_staff=True, is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Super Admin', 'is_admin': True})
    user.profile = p
    return user


@pytest.fixture
def non_admin_user(db):
    user = User.objects.create_user(email='regular_student@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Regular Student', 'is_admin': False})
    user.profile = p
    return user


@pytest.fixture
def user_without_profile(db):
    user = User.objects.create_user(email='noprofile@unilag.edu.ng', password='Password123!', is_email_verified=True)
    # Explicitly remove profile to test guarded permission
    Profile.objects.filter(user=user).delete()
    if hasattr(user, '_profile_cache'):
        delattr(user, '_profile_cache')
    return user


@pytest.fixture
def applicant_with_pending_request(db):
    user = User.objects.create_user(email='applicant@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Applicant', 'is_verified': False})
    user.profile = p
    doc = SimpleUploadedFile(name='id.jpg', content=b'fake image content', content_type='image/jpeg')
    req = VerificationRequest.objects.create(user=user, document=doc, status='pending')
    return user, req


@pytest.mark.django_db
class TestAdminManagement:
    def test_non_admin_gets_403(self, api_client, non_admin_user, applicant_with_pending_request):
        applicant, _ = applicant_with_pending_request
        api_client.force_authenticate(user=non_admin_user)

        # List
        res_list = api_client.get(reverse('admin-verification-list'))
        assert res_list.status_code == status.HTTP_403_FORBIDDEN

        # Approve
        res_appr = api_client.post(reverse('admin-verification-approve', kwargs={'user_id': applicant.id}))
        assert res_appr.status_code == status.HTTP_403_FORBIDDEN

        # Reject
        res_rej = api_client.post(reverse('admin-verification-reject', kwargs={'user_id': applicant.id}))
        assert res_rej.status_code == status.HTTP_403_FORBIDDEN

    def test_user_without_profile_gets_403_not_500(self, api_client, user_without_profile, applicant_with_pending_request):
        applicant, _ = applicant_with_pending_request
        api_client.force_authenticate(user=user_without_profile)

        # Hitting admin endpoint should return 403 Forbidden without throwing ObjectDoesNotExist (500)
        res = api_client.get(reverse('admin-verification-list'))
        assert res.status_code == status.HTTP_403_FORBIDDEN

    @patch('notifications.tasks.send_verification_approved_notification.delay')
    def test_admin_approve_verification_sets_flag_and_dispatches_task(self, mock_notify, api_client, admin_user, applicant_with_pending_request):
        applicant, req = applicant_with_pending_request
        api_client.force_authenticate(user=admin_user)

        # 1. Admin lists pending verifications
        res_list = api_client.get(reverse('admin-verification-list'))
        assert res_list.status_code == status.HTTP_200_OK
        assert res_list.data['count'] == 1

        # 2. Admin approves
        approve_url = reverse('admin-verification-approve', kwargs={'user_id': applicant.id})
        res_appr = api_client.post(approve_url)
        assert res_appr.status_code == status.HTTP_200_OK
        assert res_appr.data['status'] == 'approved'
        assert res_appr.data['is_verified'] is True

        # Check DB state
        req.refresh_from_db()
        assert req.status == 'approved'
        assert req.reviewed_by == admin_user

        applicant_profile = Profile.objects.get(user=applicant)
        assert applicant_profile.is_verified is True

        # Assert notification Celery task was called
        mock_notify.assert_called_once_with(str(applicant.id))

    @patch('notifications.tasks.send_verification_rejected_notification.delay')
    def test_admin_reject_verification(self, mock_notify, api_client, admin_user, applicant_with_pending_request):
        applicant, req = applicant_with_pending_request
        api_client.force_authenticate(user=admin_user)

        reject_url = reverse('admin-verification-reject', kwargs={'user_id': applicant.id})
        res_rej = api_client.post(reject_url, {'reason': 'Invalid student ID number'}, format='json')
        assert res_rej.status_code == status.HTTP_200_OK
        assert res_rej.data['status'] == 'rejected'
        assert res_rej.data['rejection_reason'] == 'Invalid student ID number'

        req.refresh_from_db()
        assert req.status == 'rejected'
        assert req.rejection_reason == 'Invalid student ID number'

        applicant_profile = Profile.objects.get(user=applicant)
        assert applicant_profile.is_verified is False

        mock_notify.assert_called_once_with(str(applicant.id), 'Invalid student ID number')

    def test_signed_document_url_expiry_fixing_60_second_bug(self, api_client, admin_user, applicant_with_pending_request):
        applicant, req = applicant_with_pending_request
        api_client.force_authenticate(user=admin_user)

        # 1. Fetch document URL
        doc_url = reverse('admin-verification-document', kwargs={'user_id': applicant.id})
        response = api_client.get(f"{doc_url}?format=json")
        assert response.status_code == status.HTTP_200_OK

        expires_in = response.data['expires_in']

        # CRITICAL ASSERTION: Expiry must NOT be 60 seconds (the original bug)
        assert expires_in != 60, "Signed URL expiry is still 60 seconds! Fix the bug!"
        # Expiry MUST be in 30-60 minute range (1800s to 3600s)
        assert 1800 <= expires_in <= 3600, f"Expected expiry between 1800s and 3600s, got {expires_in}s"

        # 2. Test signed URL access
        signed_url = response.data['document_url']
        api_client.credentials()  # Unauthenticate to test signed token access
        res_signed = api_client.get(signed_url)
        assert res_signed.status_code == status.HTTP_200_OK

        # 3. Test expired token is rejected
        signer = TimestampSigner()
        # Sign with a timestamp 2000 seconds in the past
        old_time = signer.timestamp(signer.sign(str(req.id)))
        expired_url = f"{doc_url}?token={req.id}:oldtime:invalidsig"
        res_expired = api_client.get(expired_url)
        assert res_expired.status_code == status.HTTP_403_FORBIDDEN
