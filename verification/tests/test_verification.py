import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from verification.models import VerificationRequest


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(email='student_verif@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Verif Student', 'is_verified': False})
    user.profile = p
    return user


def create_file(name='id_card.png', content=b'sample content', content_type='image/png'):
    return SimpleUploadedFile(name=name, content=content, content_type=content_type)


@pytest.mark.django_db
class TestVerification:
    def test_submit_document_starts_pending(self, api_client, student_user):
        api_client.force_authenticate(user=student_user)
        url = reverse('verification-submit')
        doc = create_file('student_id.jpg', b'\xff\xd8\xff\xe0' + b'0' * 500, 'image/jpeg')

        response = api_client.post(url, {'document': doc}, format='multipart')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['status'] == 'pending'
        assert response.data['user_id'] == str(student_user.id)

        # Check status endpoint
        status_url = reverse('verification-status')
        res_status = api_client.get(status_url)
        assert res_status.status_code == status.HTTP_200_OK
        assert res_status.data['status'] == 'pending'
        assert res_status.data['is_verified'] is False

    def test_cannot_submit_duplicate_while_pending(self, api_client, student_user):
        api_client.force_authenticate(user=student_user)
        url = reverse('verification-submit')

        # 1st submission
        doc1 = create_file('student_id.pdf', b'%PDF-1.4' + b'0' * 500, 'application/pdf')
        res1 = api_client.post(url, {'document': doc1}, format='multipart')
        assert res1.status_code == status.HTTP_201_CREATED

        # 2nd submission while pending -> rejected
        doc2 = create_file('student_id_2.pdf', b'%PDF-1.4' + b'0' * 500, 'application/pdf')
        res2 = api_client.post(url, {'document': doc2}, format='multipart')
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already have a pending' in str(res2.data).lower()

    def test_rejection_allows_resubmission_resetting_to_pending(self, api_client, student_user):
        api_client.force_authenticate(user=student_user)
        url = reverse('verification-submit')

        # 1. Initial submission
        doc = create_file('id.png', b'\x89PNG' + b'0' * 500, 'image/png')
        api_client.post(url, {'document': doc}, format='multipart')

        # 2. Simulate admin rejection
        req = VerificationRequest.objects.get(user=student_user)
        req.status = 'rejected'
        req.rejection_reason = 'Document blurry. Please re-upload.'
        req.save()

        # 3. Student resubmits new clear document
        doc2 = create_file('clear_id.png', b'\x89PNG' + b'1' * 500, 'image/png')
        res_resubmit = api_client.post(url, {'document': doc2}, format='multipart')
        assert res_resubmit.status_code == status.HTTP_201_CREATED

        req.refresh_from_db()
        assert req.status == 'pending'
        assert req.rejection_reason == ''

    def test_file_type_validation_rejects_disallowed_types(self, api_client, student_user):
        api_client.force_authenticate(user=student_user)
        url = reverse('verification-submit')

        # Attempt to upload .txt file
        txt_file = create_file('admission.txt', b'admission letter content', 'text/plain')
        res = api_client.post(url, {'document': txt_file}, format='multipart')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'unsupported' in str(res.data).lower()

    def test_file_size_validation_rejects_exceeding_5mb(self, api_client, student_user):
        api_client.force_authenticate(user=student_user)
        url = reverse('verification-submit')

        # 5MB + 1 byte
        oversized = SimpleUploadedFile(
            name='huge.pdf',
            content=b'0' * (5 * 1024 * 1024 + 10),
            content_type='application/pdf'
        )
        res = api_client.post(url, {'document': oversized}, format='multipart')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'exceeds 5mb' in str(res.data).lower()
