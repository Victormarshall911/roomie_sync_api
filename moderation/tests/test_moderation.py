import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from listings.models import Listing
from moderation.models import Report, Block


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def regular_user(db):
    user = User.objects.create_user(email='user1@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Regular User', 'is_verified': True})
    user.profile = p
    return user


@pytest.fixture
def other_user(db):
    user = User.objects.create_user(email='user2@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Other User', 'is_verified': True})
    user.profile = p
    return user


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(email='admin@unilag.edu.ng', password='Password123!', is_staff=True, is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Admin User', 'is_admin': True})
    user.profile = p
    return user


@pytest.mark.django_db
class TestModeration:
    def test_create_report_and_admin_vs_regular_visibility(self, api_client, regular_user, other_user, admin_user):
        url = reverse('report-list-create')

        # 1. Regular user reports other_user
        api_client.force_authenticate(user=regular_user)
        report_payload = {
            'reported_user_id': str(other_user.id),
            'reason': 'Inappropriate listing description with spam links.'
        }
        res_create = api_client.post(url, report_payload, format='json')
        assert res_create.status_code == status.HTTP_201_CREATED
        assert res_create.data['status'] == 'pending'
        assert res_create.data['reporter_id'] == str(regular_user.id)

        # 2. Other user reports regular_user
        api_client.force_authenticate(user=other_user)
        res_create2 = api_client.post(url, {
            'reported_user_id': str(regular_user.id),
            'reason': 'Harassment in comments.'
        }, format='json')
        assert res_create2.status_code == status.HTTP_201_CREATED

        # 3. Regular user lists reports -> should ONLY see the 1 report they created
        api_client.force_authenticate(user=regular_user)
        res_list_reg = api_client.get(url)
        assert res_list_reg.status_code == status.HTTP_200_OK
        assert res_list_reg.data['count'] == 1
        assert res_list_reg.data['results'][0]['reporter_id'] == str(regular_user.id)

        # 4. Admin user lists reports -> should see ALL reports (count == 2)
        api_client.force_authenticate(user=admin_user)
        res_list_adm = api_client.get(url)
        assert res_list_adm.status_code == status.HTTP_200_OK
        assert res_list_adm.data['count'] == 2

    def test_block_user_filters_listings_from_discovery_feed(self, api_client, regular_user, other_user):
        # Create listing owned by other_user
        listing = Listing.objects.create(
            user=other_user,
            title='Listing by Other User',
            price=120000,
            location='Yaba',
            type='Room',
            searching_for='Looking for Roommate'
        )

        listings_url = reverse('listing-list-create')
        blocks_url = reverse('block-list-create')

        api_client.force_authenticate(user=regular_user)

        # Initially, regular_user can see other_user's listing
        res1 = api_client.get(listings_url)
        assert res1.status_code == status.HTTP_200_OK
        assert res1.data['count'] == 1

        # Now regular_user blocks other_user
        res_block = api_client.post(blocks_url, {'blocked_id': str(other_user.id)}, format='json')
        assert res_block.status_code == status.HTTP_201_CREATED
        assert Block.objects.filter(blocker=regular_user, blocked=other_user).exists()

        # Listing must now disappear from regular_user's discovery feed
        res2 = api_client.get(listings_url)
        assert res2.status_code == status.HTTP_200_OK
        assert res2.data['count'] == 0

        # Unblock other_user
        unblock_url = reverse('block-destroy', kwargs={'blocked_id': other_user.id})
        res_unblock = api_client.delete(unblock_url)
        assert res_unblock.status_code == status.HTTP_204_NO_CONTENT

        # Listing reappears after unblocking
        res3 = api_client.get(listings_url)
        assert res3.status_code == status.HTTP_200_OK
        assert res3.data['count'] == 1

    def test_duplicate_block_rejected(self, api_client, regular_user, other_user):
        blocks_url = reverse('block-list-create')
        api_client.force_authenticate(user=regular_user)

        # 1st block succeeds
        res1 = api_client.post(blocks_url, {'blocked_id': str(other_user.id)}, format='json')
        assert res1.status_code == status.HTTP_201_CREATED

        # 2nd duplicate block is rejected
        res2 = api_client.post(blocks_url, {'blocked_id': str(other_user.id)}, format='json')
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already blocked' in str(res2.data).lower()

    def test_self_block_and_self_report_rejected(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)

        # Self-block
        blocks_url = reverse('block-list-create')
        res_block = api_client.post(blocks_url, {'blocked_id': str(regular_user.id)}, format='json')
        assert res_block.status_code == status.HTTP_400_BAD_REQUEST

        # Self-report
        report_url = reverse('report-list-create')
        res_report = api_client.post(report_url, {'reported_user_id': str(regular_user.id), 'reason': 'test'}, format='json')
        assert res_report.status_code == status.HTTP_400_BAD_REQUEST
