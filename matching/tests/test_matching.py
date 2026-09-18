import pytest
from types import SimpleNamespace
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from listings.models import Listing
from matching.services import calculate_match, WEIGHTS


@pytest.fixture
def api_client():
    return APIClient()


class TestMatchingServiceUnits:
    def test_weights_sum_to_one(self):
        """Confirm all 9 weights sum exactly to 1.00 (100%)."""
        assert len(WEIGHTS) == 9
        assert pytest.approx(sum(WEIGHTS.values()), rel=1e-5) == 1.00
        assert WEIGHTS['budget'] == 0.25
        assert WEIGHTS['location'] == 0.15
        assert WEIGHTS['cleanliness'] == 0.12
        assert WEIGHTS['sleep'] == 0.10
        assert WEIGHTS['noise'] == 0.10
        assert WEIGHTS['social'] == 0.08
        assert WEIGHTS['study'] == 0.08
        assert WEIGHTS['smoking'] == 0.06
        assert WEIGHTS['drinking'] == 0.06

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
        # overlap = 20000. ratio = (20000 * 2) / (50000 + 40000) = 40000 / 90000 = 4/9 = 44.44%
        p1 = SimpleNamespace(user_id='u1', budget_min=50000, budget_max=100000)
        p2 = SimpleNamespace(user_id='u2', budget_min=80000, budget_max=120000)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 44

    def test_cleanliness_difference_tolerance_hand_calculation(self):
        # clean1=6, clean2=8 -> diff=2 (<=3)
        # cleanScore = 1 - (2/6) = 4/6 = 66.67% -> rounded 67%
        p1 = SimpleNamespace(user_id='u1', cleanliness=6)
        p2 = SimpleNamespace(user_id='u2', cleanliness=8)
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 67

        # diff = 3 -> cleanScore = 1 - 3/6 = 50%
        p3 = SimpleNamespace(user_id='u3', cleanliness=9)
        score_3 = calculate_match(p1, p3, use_cache=False)
        assert score_3 == 50

        # diff = 4 (> 3) -> score = 0
        p4 = SimpleNamespace(user_id='u4', cleanliness=10)
        score_4 = calculate_match(p1, p4, use_cache=False)
        assert score_4 == 0

    def test_frontend_jest_half_match_and_cleanliness_scale(self):
        """Replicates exact test cases from RoomieSync/src/utils/matching.test.ts."""
        base_profile = SimpleNamespace(
            user_id='u1',
            budget_min=10000,
            budget_max=50000,
            location_preference='Mainland',
            sleep_habit='Early Bird',
            cleanliness=8,
            socializing='Rarely',
            smoking='No',
            noise_level='Moderate',
            study_time='Morning',
            drinking_habit='Rarely/Never',
        )

        # 1. Half match: loses sleep (10), noise (10), study (8), social (8), drinking (6), smoking (6)
        # Retains Budget (25), Location (15), Cleanliness (12) -> total = 52
        half_match = SimpleNamespace(
            user_id='u2',
            budget_min=10000,
            budget_max=50000,
            location_preference='Mainland',
            cleanliness=8,
            sleep_habit='Night Owl',
            noise_level='Lively',
            study_time='Night',
            socializing='Guests often',
            drinking_habit='Often',
            smoking='Yes',
        )
        assert calculate_match(base_profile, half_match, use_cache=False) == 52

        # 2. Cleanliness 6 vs 3 (diff 3): cleanScore = 1 - 3/6 = 0.5. Total score = 100 - (0.5 * 12) = 94
        p_clean6 = SimpleNamespace(
            user_id='u3',
            budget_min=10000,
            budget_max=50000,
            location_preference='Mainland',
            cleanliness=6,
            sleep_habit='Early Bird',
            socializing='Rarely',
            smoking='No',
            noise_level='Moderate',
            study_time='Morning',
            drinking_habit='Rarely/Never',
        )
        p_clean3 = SimpleNamespace(
            user_id='u4',
            budget_min=10000,
            budget_max=50000,
            location_preference='Mainland',
            cleanliness=3,
            sleep_habit='Early Bird',
            socializing='Rarely',
            smoking='No',
            noise_level='Moderate',
            study_time='Morning',
            drinking_habit='Rarely/Never',
        )
        assert calculate_match(p_clean6, p_clean3, use_cache=False) == 94

    def test_substring_location_match_hand_calculation(self):
        # loc1='yaba, lagos', loc2='yaba' -> 70% partial match
        p1 = SimpleNamespace(user_id='u1', location_preference='Yaba, Lagos')
        p2 = SimpleNamespace(user_id='u2', location_preference='Yaba')
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 70

    def test_study_time_and_drinking_habit_evaluated(self):
        # Study time: 8%
        p1 = SimpleNamespace(user_id='u1', study_time='Night')
        p2 = SimpleNamespace(user_id='u2', study_time='Night')
        p3 = SimpleNamespace(user_id='u3', study_time='Morning')
        assert calculate_match(p1, p2, use_cache=False) == 100
        assert calculate_match(p1, p3, use_cache=False) == 0

        # Drinking habit: 6%
        pd1 = SimpleNamespace(user_id='u1', drinking_habit='Socially')
        pd2 = SimpleNamespace(user_id='u2', drinking_habit='Socially')
        pd3 = SimpleNamespace(user_id='u3', drinking_habit='Often')
        assert calculate_match(pd1, pd2, use_cache=False) == 100
        assert calculate_match(pd1, pd3, use_cache=False) == 0

    def test_mixed_9_traits_hand_calculation(self):
        """
        Calculates exact expected composite score across all 9 traits:
          1. Budget: [100k, 200k] vs [150k, 250k] -> ratio 0.5 * 0.25 = 0.125
          2. Location: 'Akoka, Yaba' vs 'Akoka' -> partial 0.7 * 0.15 = 0.105
          3. Cleanliness: 9 vs 6 -> diff 3 -> (1 - 3/6) * 0.12 = 0.060
          4. Sleep: 'Night Owl' vs 'Night Owl' -> match 1.0 * 0.10 = 0.100
          5. Noise: 'Quiet' vs 'Quiet' -> match 1.0 * 0.10 = 0.100
          6. Social: 'Rarely' vs 'Rarely' -> match 1.0 * 0.08 = 0.080
          7. Study: 'Night' vs 'Morning' -> mismatch 0.0 * 0.08 = 0.000
          8. Smoking: 'No' vs 'No' -> match 1.0 * 0.06 = 0.060
          9. Drinking: 'Socially' vs 'Often' -> mismatch 0.0 * 0.06 = 0.000
          Total Weight = 1.00
          Total Score = 0.125 + 0.105 + 0.060 + 0.100 + 0.100 + 0.080 + 0.060 = 0.630
          Expected Score = 63%
        """
        p1 = SimpleNamespace(
            user_id='u1',
            budget_min=100000,
            budget_max=200000,
            location_preference='Akoka, Yaba',
            cleanliness=9,
            sleep_habit='Night Owl',
            noise_level='Quiet',
            socializing='Rarely',
            study_time='Night',
            smoking='No',
            drinking_habit='Socially'
        )
        p2 = SimpleNamespace(
            user_id='u2',
            budget_min=150000,
            budget_max=250000,
            location_preference='Akoka',
            cleanliness=6,
            sleep_habit='Night Owl',
            noise_level='Quiet',
            socializing='Rarely',
            study_time='Morning',
            smoking='No',
            drinking_habit='Often'
        )
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 63

    def test_missing_traits_excluded_from_denominator_not_penalized(self):
        # Both only set study='Night' and drinking='Socially'. Both match 100%.
        # Total weight = 0.08 + 0.06 = 0.14. Score = 0.14.
        # Ratio = 100%, NOT 14%!
        p1 = SimpleNamespace(user_id='u1', study_time='Night', drinking_habit='Socially')
        p2 = SimpleNamespace(user_id='u2', study_time='Night', drinking_habit='Socially')
        score = calculate_match(p1, p2, use_cache=False)
        assert score == 100

    def test_no_common_attributes_returns_50_fallback(self):
        p1 = SimpleNamespace(user_id='u1', sleep_habit='Night Owl')
        p2 = SimpleNamespace(user_id='u2', noise_level='Quiet')
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
                'sleep_habit': 'Early Bird',
                'study_time': 'Night',
                'drinking_habit': 'Socially'
            }
        )
        u1.profile = p1

        # User 2: Great match (Same budget, location, cleanliness 9, Early Bird, study Night, drinking Socially)
        u2 = User.objects.create_user(email='great_match@unilag.edu.ng', password='Password123!')
        p2, _ = Profile.objects.update_or_create(
            user=u2,
            defaults={
                'full_name': 'Great Match',
                'budget_min': 50000,
                'budget_max': 100000,
                'location_preference': 'Akoka',
                'cleanliness': 9,
                'sleep_habit': 'Early Bird',
                'study_time': 'Night',
                'drinking_habit': 'Socially'
            }
        )
        u2.profile = p2

        # User 3: Poor match (Non-overlapping budget, different location, cleanliness 1, Night Owl, study Morning, drinking Often)
        u3 = User.objects.create_user(email='poor_match@unilag.edu.ng', password='Password123!')
        p3, _ = Profile.objects.update_or_create(
            user=u3,
            defaults={
                'full_name': 'Poor Match',
                'budget_min': 200000,
                'budget_max': 350000,
                'location_preference': 'Ikorodu',
                'cleanliness': 1,
                'sleep_habit': 'Night Owl',
                'study_time': 'Morning',
                'drinking_habit': 'Often'
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
