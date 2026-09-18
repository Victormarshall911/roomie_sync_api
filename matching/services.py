from django.core.cache import cache

WEIGHTS = {
    'budget': 0.25,
    'location': 0.15,
    'cleanliness': 0.12,
    'sleep': 0.10,
    'noise': 0.10,
    'social': 0.08,
    'study': 0.08,
    'smoking': 0.06,
    'drinking': 0.06,
}


def calculate_match(p1, p2, use_cache: bool = True) -> int:
    """
    Pure Python service calculating the roommate compatibility percentage
    between profile p1 and profile p2 using the exact weighted algorithm.
    Excludes unset/missing optional traits from the denominator (totalWeight).
    Falls back to 50% baseline if no common attributes exist.
    """
    if p1 is None or p2 is None:
        return 50

    # If same profile or user
    p1_id = getattr(p1, 'user_id', None) or getattr(p1, 'id', None)
    p2_id = getattr(p2, 'user_id', None) or getattr(p2, 'id', None)
    if p1_id and p2_id and p1_id == p2_id:
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
    p1_bmin = getattr(p1, 'budget_min', None)
    p1_bmax = getattr(p1, 'budget_max', None)
    p2_bmin = getattr(p2, 'budget_min', None)
    p2_bmax = getattr(p2, 'budget_max', None)

    if None not in (p1_bmin, p1_bmax, p2_bmin, p2_bmax):
        total_weight += WEIGHTS['budget']
        max_min = max(p1_bmin, p2_bmin)
        min_max = min(p1_bmax, p2_bmax)

        if max_min <= min_max:
            overlap_range = min_max - max_min
            p1_range = (p1_bmax - p1_bmin) or 1
            p2_range = (p2_bmax - p2_bmin) or 1
            overlap_ratio = (overlap_range * 2.0) / (p1_range + p2_range)
            score += min(overlap_ratio, 1.0) * WEIGHTS['budget']

    # 2. Location Preference (15%)
    loc1 = (getattr(p1, 'location_preference', '') or '').strip().lower()
    loc2 = (getattr(p2, 'location_preference', '') or '').strip().lower()
    if loc1 and loc2:
        total_weight += WEIGHTS['location']
        if loc1 == loc2:
            score += WEIGHTS['location']
        elif loc1 in loc2 or loc2 in loc1:
            score += WEIGHTS['location'] * 0.7

    # 3. Sleep Habit (10%)
    sleep1 = getattr(p1, 'sleep_habit', None)
    sleep2 = getattr(p2, 'sleep_habit', None)
    if sleep1 and sleep2:
        total_weight += WEIGHTS['sleep']
        if sleep1 == sleep2:
            score += WEIGHTS['sleep']

    # 4. Cleanliness (12%)
    clean1 = getattr(p1, 'cleanliness', None)
    clean2 = getattr(p2, 'cleanliness', None)
    if clean1 is not None and clean2 is not None:
        total_weight += WEIGHTS['cleanliness']
        clean_diff = abs(clean1 - clean2)
        if clean_diff == 0:
            score += WEIGHTS['cleanliness']
        elif clean_diff <= 3:
            clean_score = 1.0 - (clean_diff / 6.0)
            score += clean_score * WEIGHTS['cleanliness']

    # 5. Noise Level (10%)
    noise1 = getattr(p1, 'noise_level', None)
    noise2 = getattr(p2, 'noise_level', None)
    if noise1 and noise2:
        total_weight += WEIGHTS['noise']
        if noise1 == noise2:
            score += WEIGHTS['noise']

    # 6. Socializing (8%)
    social1 = getattr(p1, 'socializing', None)
    social2 = getattr(p2, 'socializing', None)
    if social1 and social2:
        total_weight += WEIGHTS['social']
        if social1 == social2:
            score += WEIGHTS['social']

    # 7. Study Time (8%)
    study1 = getattr(p1, 'study_time', None)
    study2 = getattr(p2, 'study_time', None)
    if study1 and study2:
        total_weight += WEIGHTS['study']
        if study1 == study2:
            score += WEIGHTS['study']

    # 8. Smoking (6%)
    smoke1 = getattr(p1, 'smoking', None)
    smoke2 = getattr(p2, 'smoking', None)
    if smoke1 and smoke2:
        total_weight += WEIGHTS['smoking']
        if smoke1 == smoke2:
            score += WEIGHTS['smoking']

    # 9. Drinking Habit (6%)
    drink1 = getattr(p1, 'drinking_habit', None)
    drink2 = getattr(p2, 'drinking_habit', None)
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
