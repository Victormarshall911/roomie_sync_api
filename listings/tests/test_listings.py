import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from listings.models import Listing, ListingImage


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def verified_user(db):
    user = User.objects.create_user(
        email='verified_student@unilag.edu.ng',
        password='Password123!',
        is_email_verified=True
    )
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={'full_name': 'Verified Student', 'is_verified': True}
    )
    user.profile = profile
    return user


@pytest.fixture
def unverified_user(db):
    user = User.objects.create_user(
        email='unverified_student@unilag.edu.ng',
        password='Password123!',
        is_email_verified=True
    )
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={'full_name': 'Unverified Student', 'is_verified': False}
    )
    user.profile = profile
    return user


@pytest.fixture
def other_verified_user(db):
    user = User.objects.create_user(
        email='other_student@unilag.edu.ng',
        password='Password123!',
        is_email_verified=True
    )
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={'full_name': 'Other Student', 'is_verified': True}
    )
    user.profile = profile
    return user


def create_dummy_image(name='test.png'):
    return SimpleUploadedFile(
        name=name,
        content=b'GIF89a\x01\x00\x01\x00\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
        content_type='image/png'
    )


@pytest.mark.django_db
class TestListings:
    def test_create_listing_unauthenticated_rejected(self, api_client):
        url = reverse('listing-list-create')
        payload = {
            'title': 'Spacious Room in Yaba',
            'price': 120000,
            'location': 'Yaba, Lagos',
            'type': 'Room',
            'searching_for': 'Looking for Roommate',
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_listing_unverified_student_rejected(self, api_client, unverified_user):
        api_client.force_authenticate(user=unverified_user)
        url = reverse('listing-list-create')
        payload = {
            'title': 'Spacious Room in Yaba',
            'price': 120000,
            'location': 'Yaba, Lagos',
            'type': 'Room',
            'searching_for': 'Looking for Roommate',
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert 'Only verified students' in str(response.data)

    def test_create_listing_verified_student_succeeds(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        url = reverse('listing-list-create')
        payload = {
            'title': 'Spacious Room in Yaba',
            'description': 'Close to UNILAG campus gate.',
            'price': 120000,
            'location': 'Yaba, Lagos',
            'type': 'Room',
            'searching_for': 'Looking for Roommate',
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == 'Spacious Room in Yaba'
        assert response.data['user_id'] == str(verified_user.id)
        assert response.data['is_available'] is True

    def test_create_listing_with_multiple_images_and_ordering(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        url = reverse('listing-list-create')

        img1 = create_dummy_image('room1.png')
        img2 = create_dummy_image('room2.png')

        payload = {
            'title': 'Duplex Room with Images',
            'price': 200000,
            'location': 'Akoka, Lagos',
            'type': 'Room',
            'searching_for': 'Listing a Space',
            'uploaded_images': [img1, img2]
        }
        response = api_client.post(url, payload, format='multipart')
        assert response.status_code == status.HTTP_201_CREATED

        listing_id = response.data['id']
        images = ListingImage.objects.filter(listing_id=listing_id).order_by('order')
        assert images.count() == 2
        assert images[0].order == 0
        assert images[1].order == 1

    def test_update_and_delete_owner_vs_non_owner(self, api_client, verified_user, other_verified_user):
        listing = Listing.objects.create(
            user=verified_user,
            title='Cozy Flat',
            price=150000,
            location='Surulere',
            type='Room',
            searching_for='Looking for Roommate'
        )
        url = reverse('listing-detail', kwargs={'pk': listing.id})

        # 1. Non-owner cannot update
        api_client.force_authenticate(user=other_verified_user)
        res_update_fail = api_client.patch(url, {'price': 90000}, format='json')
        assert res_update_fail.status_code == status.HTTP_403_FORBIDDEN

        # 2. Non-owner cannot delete
        res_del_fail = api_client.delete(url)
        assert res_del_fail.status_code == status.HTTP_403_FORBIDDEN

        # 3. Owner can update
        api_client.force_authenticate(user=verified_user)
        res_update_ok = api_client.patch(url, {'price': 175000}, format='json')
        assert res_update_ok.status_code == status.HTTP_200_OK
        assert res_update_ok.data['price'] == 175000

        # 4. Owner can delete
        res_del_ok = api_client.delete(url)
        assert res_del_ok.status_code == status.HTTP_204_NO_CONTENT
        assert not Listing.objects.filter(id=listing.id).exists()

    def test_toggle_availability(self, api_client, verified_user, other_verified_user):
        listing = Listing.objects.create(
            user=verified_user,
            title='Available Room',
            price=80000,
            location='Bariga',
            type='Room',
            searching_for='Looking for Roommate',
            is_available=True
        )
        url = reverse('listing-toggle-availability', kwargs={'pk': listing.id})

        # Non-owner attempt -> 403
        api_client.force_authenticate(user=other_verified_user)
        res_fail = api_client.post(url)
        assert res_fail.status_code == status.HTTP_403_FORBIDDEN

        # Owner toggle 1: True -> False
        api_client.force_authenticate(user=verified_user)
        res_toggle1 = api_client.post(url)
        assert res_toggle1.status_code == status.HTTP_200_OK
        assert res_toggle1.data['is_available'] is False
        listing.refresh_from_db()
        assert listing.is_available is False

        # Owner toggle 2: False -> True
        res_toggle2 = api_client.post(url)
        assert res_toggle2.status_code == status.HTTP_200_OK
        assert res_toggle2.data['is_available'] is True
        listing.refresh_from_db()
        assert listing.is_available is True

    def test_pagination_returns_page_size_20(self, api_client, verified_user):
        for i in range(25):
            Listing.objects.create(
                user=verified_user,
                title=f'Listing {i}',
                price=50000 + (i * 1000),
                location='Yaba',
                type='Room',
                searching_for='Looking for Roommate'
            )

        url = reverse('listing-list-create')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 25
        assert len(response.data['results']) == 20
        assert response.data['next'] is not None

    def test_filters(self, api_client, verified_user):
        Listing.objects.create(
            user=verified_user,
            title='Affordable Flat in Ikeja',
            price=50000,
            location='Ikeja, Lagos',
            type='Room',
            searching_for='Looking for Roommate'
        )
        Listing.objects.create(
            user=verified_user,
            title='Luxury Flat in Lekki',
            price=250000,
            location='Lekki Phase 1',
            type='Roommate',
            searching_for='Listing a Space'
        )

        url = reverse('listing-list-create')

        # Filter by searching_for
        res_search = api_client.get(f"{url}?searching_for=Listing a Space")
        assert res_search.data['count'] == 1
        assert res_search.data['results'][0]['title'] == 'Luxury Flat in Lekki'

        # Filter by budget range (price >= 100000)
        res_price = api_client.get(f"{url}?min_price=100000")
        assert res_price.data['count'] == 1
        assert res_price.data['results'][0]['price'] == 250000

        # Filter by location
        res_loc = api_client.get(f"{url}?location=ikeja")
        assert res_loc.data['count'] == 1
        assert res_loc.data['results'][0]['title'] == 'Affordable Flat in Ikeja'
