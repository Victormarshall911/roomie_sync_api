import pytest
from unittest.mock import patch
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_with_profile(db):
    user = User.objects.create_user(
        email='student1@unilag.edu.ng',
        password='Password123!',
        is_email_verified=True
    )
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={
            'full_name': 'Adeola Johnson',
            'university': 'University of Lagos',
            'department': 'Computer Science',
            'gender': 'Female',
            'budget_min': 50000,
            'budget_max': 150000,
            'location_preference': 'Akoka',
            'cleanliness': 8,
            'sleep_habit': 'Night Owl',
            'socializing': 'Guests often',
            'smoking': 'No',
            'noise_level': 'Moderate',
            'study_time': 'Night',
            'drinking_habit': 'Socially',
            'pets_preference': 'Okay with them',
            'is_admin': False,
        }
    )
    return user, profile


@pytest.fixture
def other_user_with_profile(db):
    user = User.objects.create_user(
        email='student2@unilag.edu.ng',
        password='Password123!',
        is_email_verified=True
    )
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={
            'full_name': 'Chidi Obi',
            'university': 'University of Lagos',
            'department': 'Electrical Engineering',
            'gender': 'Male',
            'budget_min': 60000,
            'budget_max': 180000,
            'location_preference': 'Yaba',
            'cleanliness': 7,
            'sleep_habit': 'Night Owl',
            'is_admin': True,  # Test that is_admin is not exposed publicly
        }
    )
    return user, profile


@pytest.mark.django_db
class TestProfiles:
    @patch('accounts.tasks.send_verification_email.delay')
    def test_registration_with_onboarding_profile_payload(self, mock_email, api_client):
        url = reverse('auth-register')
        payload = {
            'email': 'onboarding_user@example.com',
            'password': 'Password123!',
            'profile': {
                'full_name': 'Emeka Okafor',
                'university': 'University of Ibadan',
                'department': 'Pharmacy',
                'gender': 'Male',
                'budget_min': 40000,
                'budget_max': 120000,
                'location_preference': 'Agbowo',
                'cleanliness': 9,
                'sleep_habit': 'Early Bird',
                'smoking': 'No',
            }
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email='onboarding_user@example.com')
        profile = Profile.objects.get(user=user)
        assert profile.full_name == 'Emeka Okafor'
        assert profile.university == 'University of Ibadan'
        assert profile.department == 'Pharmacy'
        assert profile.gender == 'Male'
        assert profile.budget_min == 40000
        assert profile.budget_max == 120000
        assert profile.cleanliness == 9
        assert profile.sleep_habit == 'Early Bird'
        assert profile.smoking == 'No'

    def test_fetch_own_profile(self, api_client, user_with_profile):
        user, profile = user_with_profile
        api_client.force_authenticate(user=user)

        url = reverse('profile-me')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(user.id)
        assert response.data['email'] == user.email
        assert response.data['full_name'] == 'Adeola Johnson'
        assert response.data['university'] == 'University of Lagos'
        assert 'is_admin' in response.data
        assert response.data['is_admin'] is False

    def test_partial_update_profile_groups(self, api_client, user_with_profile):
        user, profile = user_with_profile
        api_client.force_authenticate(user=user)
        url = reverse('profile-me')

        # 1. Update budget group
        res1 = api_client.patch(url, {'budget_min': 70000, 'budget_max': 200000}, format='json')
        assert res1.status_code == status.HTTP_200_OK
        assert res1.data['budget_min'] == 70000
        assert res1.data['budget_max'] == 200000

        # 2. Update lifestyle group
        res2 = api_client.patch(url, {
            'cleanliness': 9,
            'noise_level': 'Quiet',
            'socializing': 'Rarely',
            'sleep_habit': 'Early Bird'
        }, format='json')
        assert res2.status_code == status.HTTP_200_OK
        assert res2.data['cleanliness'] == 9
        assert res2.data['noise_level'] == 'Quiet'
        assert res2.data['socializing'] == 'Rarely'
        assert res2.data['sleep_habit'] == 'Early Bird'

        # 3. Update search status
        res3 = api_client.patch(url, {'searching_for': 'Listing a Space'}, format='json')
        assert res3.status_code == status.HTTP_200_OK
        assert res3.data['searching_for'] == 'Listing a Space'

        # 4. Attempt to self-elevate to is_admin or is_verified (read-only)
        res4 = api_client.patch(url, {'is_admin': True, 'is_verified': True}, format='json')
        assert res4.status_code == status.HTTP_200_OK
        profile.refresh_from_db()
        assert profile.is_admin is False
        assert profile.is_verified is False

    def test_fetch_public_profile_hides_private_fields(self, api_client, user_with_profile, other_user_with_profile):
        user, _ = user_with_profile
        other_user, other_profile = other_user_with_profile
        api_client.force_authenticate(user=user)

        url = reverse('profile-detail', kwargs={'pk': other_user.id})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(other_user.id)
        assert response.data['full_name'] == other_profile.full_name
        assert response.data['university'] == other_profile.university

        # Confirm private fields are NOT exposed on public profile
        assert 'is_admin' not in response.data
        assert 'email' not in response.data

    def test_auto_creation_fallback_for_bare_user(self, db):
        bare_user = User.objects.create_user(email='bare_user@example.com', password='Password123!')
        assert hasattr(bare_user, 'profile')
        assert bare_user.profile is not None
        assert bare_user.profile.full_name == 'bare_user'
