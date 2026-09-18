from django.core.cache import cache

# Authoritative weights from RoomieSync/src/utils/matching.ts:35-45 and BACKEND_AUDIT.md:290-304
WEIGHTS = {
    'budget': 0.25,       # 25% Budget Overlap ratio
    'location': 0.15,     # 15% Location preference (100% exact, 70% substring partial)
    'cleanliness': 0.12,  # 12% Cleanliness (exact = 100%, diff <= 3 scores 1 - diff/6)
    'sleep': 0.10,        # 10% Sleep habit ('Early Bird' vs 'Night Owl')
    'noise': 0.10,        # 10% Noise level ('Quiet', 'Moderate', 'Lively')
    'social': 0.08,       # 8% Socializing ('Guests often' vs 'Rarely')
    'study': 0.08,        # 8% Study time ('Morning', 'Night', 'Varies')
    'smoking': 0.06,      # 6% Smoking ('Yes' vs 'No')
    'drinking': 0.06,     # 6% Drinking habit ('Often', 'Socially', 'Rarely/Never')
}


def _get_field(obj, attr_name):
    """Safely extracts field from a Django model instance, dict, or object."""
    if isinstance(obj, dict):
        return obj.get(attr_name)
    return getattr(obj, attr_name, None)


def calculate_match(p1, p2, use_cache: bool = True) -> int:
    """
    Faithful Python port of calculateMatchPercentage from RoomieSync/src/utils/matching.ts.
    
    Traits evaluated (9 total):
      1. budget (25%): overlap ratio ((minMax - maxMin) * 2) / (range1 + range2)
      2. location (15%): exact match = 100%, substring containment = 70%
      3. cleanliness (12%): exact match = 100%, abs diff <= 3 scores 1 - (diff / 6)
      4. sleep (10%): exact match = 100%
      5. noise (10%): exact match = 100%
      6. social (8%): exact match = 100%
      7. study (8%): exact match = 100%
      8. smoking (6%): exact match = 100%
      9. drinking (6%): exact match = 100%

    Normalization:
      - Only attributes present in both profiles contribute to total_weight.
      - If total_weight == 0 (no common answered attributes), returns baseline 50%.
      - Final score is rounded to the nearest integer: round((score / total_weight) * 100).
    """
    if p1 is None or p2 is None:
        return 50

    p1_id = _get_field(p1, 'user_id') or _get_field(p1, 'id')
    p2_id = _get_field(p2, 'user_id') or _get_field(p2, 'id')
    if p1_id and p2_id and str(p1_id) == str(p2_id):
        return 100

    cache_key = None
    if use_cache and p1_id and p2_id:
        min_id, max_id = min(str(p1_id), str(p2_id)), max(str(p1_id), str(p2_id))
        cache_key = f"match:{min_id}:{max_id}"
        cached_score = cache.get(cache_key)
        if cached_score is not None:
            return int(cached_score)

    score = 0.0
    total_weight = 0.0

    # 1. Budget Overlap (25%)
    bmin1 = _get_field(p1, 'budget_min')
    bmax1 = _get_field(p1, 'budget_max')
    bmin2 = _get_field(p2, 'budget_min')
    bmax2 = _get_field(p2, 'budget_max')

    if None not in (bmin1, bmax1, bmin2, bmax2):
        total_weight += WEIGHTS['budget']
        max_min = max(bmin1, bmin2)
        min_max = min(bmax1, bmax2)

        if max_min <= min_max:
            overlap_range = min_max - max_min
            p1_range = (bmax1 - bmin1) or 1
            p2_range = (bmax2 - bmin2) or 1
            overlap_ratio = (overlap_range * 2.0) / (p1_range + p2_range)
            score += min(overlap_ratio, 1.0) * WEIGHTS['budget']

    # 2. Location Preference (15%)
    raw_loc1 = _get_field(p1, 'location_preference')
    raw_loc2 = _get_field(p2, 'location_preference')
    if raw_loc1 and raw_loc2:
        loc1 = str(raw_loc1).strip().lower()
        loc2 = str(raw_loc2).strip().lower()
        if loc1 and loc2:
            total_weight += WEIGHTS['location']
            if loc1 == loc2:
                score += WEIGHTS['location']
            elif loc1 in loc2 or loc2 in loc1:
                score += WEIGHTS['location'] * 0.7

    # 3. Sleep Habit (10%)
    sleep1 = _get_field(p1, 'sleep_habit')
    sleep2 = _get_field(p2, 'sleep_habit')
    if sleep1 and sleep2:
        total_weight += WEIGHTS['sleep']
        if sleep1 == sleep2:
            score += WEIGHTS['sleep']

    # 4. Cleanliness (12%) - 3/6/9 scale (diff <= 3 is considered adjacent or matching)
    clean1 = _get_field(p1, 'cleanliness')
    clean2 = _get_field(p2, 'cleanliness')
    if clean1 is not None and clean2 is not None:
        total_weight += WEIGHTS['cleanliness']
        clean_diff = abs(clean1 - clean2)
        if clean_diff == 0:
            score += WEIGHTS['cleanliness']
        elif clean_diff <= 3:
            clean_score = 1.0 - (clean_diff / 6.0)
            score += clean_score * WEIGHTS['cleanliness']

    # 5. Noise Level (10%)
    noise1 = _get_field(p1, 'noise_level')
    noise2 = _get_field(p2, 'noise_level')
    if noise1 and noise2:
        total_weight += WEIGHTS['noise']
        if noise1 == noise2:
            score += WEIGHTS['noise']

    # 6. Socializing (8%)
    social1 = _get_field(p1, 'socializing')
    social2 = _get_field(p2, 'socializing')
    if social1 and social2:
        total_weight += WEIGHTS['social']
        if social1 == social2:
            score += WEIGHTS['social']

    # 7. Study Time (8%)
    study1 = _get_field(p1, 'study_time')
    study2 = _get_field(p2, 'study_time')
    if study1 and study2:
        total_weight += WEIGHTS['study']
        if study1 == study2:
            score += WEIGHTS['study']

    # 8. Smoking (6%)
    smoke1 = _get_field(p1, 'smoking')
    smoke2 = _get_field(p2, 'smoking')
    if smoke1 and smoke2:
        total_weight += WEIGHTS['smoking']
        if smoke1 == smoke2:
            score += WEIGHTS['smoking']

    # 9. Drinking Habit (6%)
    drink1 = _get_field(p1, 'drinking_habit')
    drink2 = _get_field(p2, 'drinking_habit')
    if drink1 and drink2:
        total_weight += WEIGHTS['drinking']
        if drink1 == drink2:
            score += WEIGHTS['drinking']

    if total_weight == 0:
        final_score = 50
    else:
        final_score = int(round((score / total_weight) * 100))

    if cache_key:
        cache.set(cache_key, final_score, timeout=86400)

    return final_score
