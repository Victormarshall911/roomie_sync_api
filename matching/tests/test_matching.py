import pytest
from types import SimpleNamespace
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from listings.models import Listing
from matching.services import calculate_match


@pytest.fixture
def api_client():
    return APIClient()


class TestMatchingServiceUnits:
    def test_identical_profiles_score_100(self):
        p1 = SimpleNamespace(
            user_id='00000000-0000-0000-0000-000000000001',
            budget_min=50000,
            budget_max=100000,
            location_preference='Yaba',
            cleanliness=8,
            sleep_habit='Night Owl',
            noise_level='Quiet',
            socializing='Rarely',
            study_time='Night',
            smoking='No',
            drinking_habit='Rarely/Never'
        )
        p2 = SimpleNamespace(
            user_id='00000000-0000-0000-0000-000000000002',
            budget_min=50000,
            budget_max=100000,
            location_preference='Yaba',
            cleanliness=8,
            sleep_habit='Night Owl',
            noise_level='Quiet',
            socializing='Rarely',
            study_time='Night',
            smoking='No',
            drinking_habit='Rarely/Never'
        )
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 100

    def test_completely_opposite_profiles_score_0(self):
        p1 = SimpleNamespace(
            user_id='00000000-0000-0000-0000-000000000001',
            budget_min=10000,
            budget_max=30000,
            location_preference='Akoka',
            cleanliness=1,
            sleep_habit='Night Owl',
            noise_level='Quiet',
            socializing='Rarely',
            study_time='Night',
            smoking='No',
            drinking_habit='Rarely/Never'
        )
        p2 = SimpleNamespace(
            user_id='00000000-0000-0000-0000-000000000002',
            budget_min=50000,
            budget_max=80000,
            location_preference='Ikeja',
            cleanliness=10,
            sleep_habit='Early Bird',
            noise_level='Lively',
            socializing='Guests often',
            study_time='Morning',
            smoking='Yes',
            drinking_habit='Often'
        )
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 0

    def test_partial_budget_overlap_hand_calculation(self):
        # p1: [50000, 100000] -> range 50000
        # p2: [80000, 120000] -> range 40000
        # overlap = 20000. ratio = 40000 / 90000 = 4/9 = 44.44%
        p1 = SimpleNamespace(user_id='u1', budget_min=50000, budget_max=100000, location_preference=None, cleanliness=None, sleep_habit=None, noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        p2 = SimpleNamespace(user_id='u2', budget_min=80000, budget_max=120000, location_preference=None, cleanliness=None, sleep_habit=None, noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 44

    def test_cleanliness_difference_tolerance_hand_calculation(self):
        # clean1=6, clean2=8 -> diff=2 (<=3)
        # cleanScore = 1 - (2/6) = 4/6 = 66.67% -> rounded 67%
        p1 = SimpleNamespace(user_id='u1', budget_min=None, budget_max=None, location_preference=None, cleanliness=6, sleep_habit=None, noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        p2 = SimpleNamespace(user_id='u2', budget_min=None, budget_max=None, location_preference=None, cleanliness=8, sleep_habit=None, noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 67

    def test_substring_location_match_hand_calculation(self):
        # loc1='yaba, lagos', loc2='yaba' -> 70% partial match
        p1 = SimpleNamespace(user_id='u1', budget_min=None, budget_max=None, location_preference='Yaba, Lagos', cleanliness=None, sleep_habit=None, noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        p2 = SimpleNamespace(user_id='u2', budget_min=None, budget_max=None, location_preference='Yaba', cleanliness=None, sleep_habit=None, noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 70

    def test_missing_traits_excluded_from_denominator_not_penalized(self):
        # Both only set sleep='Night Owl' and smoking='No'. Both match 100%.
        # Total weight = 0.10 + 0.06 = 0.16. Score = 0.16.
        # Ratio = 100%, NOT 16%!
        p1 = SimpleNamespace(user_id='u1', budget_min=None, budget_max=None, location_preference=None, cleanliness=None, sleep_habit='Night Owl', noise_level=None, socializing=None, study_time=None, smoking='No', drinking_habit=None)
        p2 = SimpleNamespace(user_id='u2', budget_min=None, budget_max=None, location_preference=None, cleanliness=None, sleep_habit='Night Owl', noise_level=None, socializing=None, study_time=None, smoking='No', drinking_habit=None)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 100

    def test_no_common_attributes_returns_50_fallback(self):
        p1 = SimpleNamespace(user_id='u1', budget_min=None, budget_max=None, location_preference=None, cleanliness=None, sleep_habit='Night Owl', noise_level=None, socializing=None, study_time=None, smoking=None, drinking_habit=None)
        p2 = SimpleNamespace(user_id='u2', budget_min=None, budget_max=None, location_preference=None, cleanliness=None, sleep_habit=None, noise_level='Quiet', socializing=None, study_time=None, smoking=None, drinking_habit=None)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 50


@pytest.mark.django_db
class TestMatchingIntegration:
    def test_matches_endpoint_and_computed_serializer_fields(self, api_client):
        # User 1: Viewer
        u1 = User.objects.create_user(email='viewer@unilag.edu.ng', password='Password123!')
        p1, _ = Profile.objects.update_or_create(
            user=u1,
            defaults={
                'full_name': 'Viewer User',
                'budget_min': 50000,
                'budget_max': 100000,
                'location_preference': 'Akoka',
                'cleanliness': 9,
                'sleep_habit': 'Early Bird'
            }
        )
        u1.profile = p1

        # User 2: Great match (Same budget, location, cleanliness 9, Early Bird)
        u2 = User.objects.create_user(email='great_match@unilag.edu.ng', password='Password123!')
        p2, _ = Profile.objects.update_or_create(
            user=u2,
            defaults={
                'full_name': 'Great Match',
                'budget_min': 50000,
                'budget_max': 100000,
                'location_preference': 'Akoka',
                'cleanliness': 9,
                'sleep_habit': 'Early Bird'
            }
        )
        u2.profile = p2

        # User 3: Poor match (Non-overlapping budget, different location, cleanliness 1, Night Owl)
        u3 = User.objects.create_user(email='poor_match@unilag.edu.ng', password='Password123!')
        p3, _ = Profile.objects.update_or_create(
            user=u3,
            defaults={
                'full_name': 'Poor Match',
                'budget_min': 200000,
                'budget_max': 350000,
                'location_preference': 'Ikorodu',
                'cleanliness': 1,
                'sleep_habit': 'Night Owl'
            }
        )
        u3.profile = p3

        api_client.force_authenticate(user=u1)

        # 1. Test /api/v1/matches/ endpoint returns sorted order
        url = reverse('matches-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data
        assert len(results) == 2
        assert results[0]['full_name'] == 'Great Match'
        assert results[0]['match_percentage'] == 100
        assert results[1]['full_name'] == 'Poor Match'
        assert results[1]['match_percentage'] == 0

        # 2. Test ListingSerializer computed match_percentage
        listing = Listing.objects.create(
            user=u2,
            title='Room by Great Match',
            price=90000,
            location='Akoka',
            type='Room',
            searching_for='Looking for Roommate'
        )
        listing_url = reverse('listing-detail', kwargs={'pk': listing.id})
        res_listing = api_client.get(listing_url)
        assert res_listing.status_code == status.HTTP_200_OK
        assert res_listing.data['match_percentage'] == 100
