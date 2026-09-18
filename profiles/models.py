from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Profile(models.Model):
    GENDER_CHOICES = (
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Non-binary', 'Non-binary'),
        ('Prefer not to say', 'Prefer not to say'),
    )

    SLEEP_HABIT_CHOICES = (
        ('Night Owl', 'Night Owl'),
        ('Early Bird', 'Early Bird'),
    )

    SOCIALIZING_CHOICES = (
        ('Guests often', 'Guests often'),
        ('Rarely', 'Rarely'),
    )

    SMOKING_CHOICES = (
        ('Yes', 'Yes'),
        ('No', 'No'),
    )

    NOISE_LEVEL_CHOICES = (
        ('Quiet', 'Quiet'),
        ('Moderate', 'Moderate'),
        ('Lively', 'Lively'),
    )

    STUDY_TIME_CHOICES = (
        ('Morning', 'Morning'),
        ('Night', 'Night'),
        ('Varies', 'Varies'),
    )

    DRINKING_HABIT_CHOICES = (
        ('Often', 'Often'),
        ('Socially', 'Socially'),
        ('Rarely/Never', 'Rarely/Never'),
    )

    PETS_PREFERENCE_CHOICES = (
        ('Love them', 'Love them'),
        ('Okay with them', 'Okay with them'),
        ('Prefer no pets', 'Prefer no pets'),
    )

    SEARCHING_FOR_CHOICES = (
        ('Looking for Roommate', 'Looking for Roommate'),
        ('Listing a Space', 'Listing a Space'),
        ('Already Matched', 'Already Matched'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='profile'
    )
    full_name = models.CharField(max_length=255, default='', blank=True)
    university = models.CharField(max_length=255, default='', blank=True)
    department = models.CharField(max_length=255, default='', blank=True)
    gender = models.CharField(max_length=30, choices=GENDER_CHOICES, blank=True, null=True)

    budget_min = models.PositiveIntegerField(default=0)
    budget_max = models.PositiveIntegerField(default=300000)
    location_preference = models.CharField(max_length=255, blank=True, default='')

    # Lifestyle attributes (used for matching)
    sleep_habit = models.CharField(max_length=30, choices=SLEEP_HABIT_CHOICES, blank=True, null=True)
    cleanliness = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        blank=True,
        null=True
    )
    socializing = models.CharField(max_length=30, choices=SOCIALIZING_CHOICES, blank=True, null=True)
    smoking = models.CharField(max_length=10, choices=SMOKING_CHOICES, blank=True, null=True)
    noise_level = models.CharField(max_length=30, choices=NOISE_LEVEL_CHOICES, blank=True, null=True)
    study_time = models.CharField(max_length=30, choices=STUDY_TIME_CHOICES, blank=True, null=True)
    drinking_habit = models.CharField(max_length=30, choices=DRINKING_HABIT_CHOICES, blank=True, null=True)
    pets_preference = models.CharField(max_length=30, choices=PETS_PREFERENCE_CHOICES, blank=True, null=True)

    avatar = models.ImageField(upload_to='avatars/%Y/%m/', null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    searching_for = models.CharField(
        max_length=50,
        choices=SEARCHING_FOR_CHOICES,
        default='Looking for Roommate'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'profiles'
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'

    def __str__(self):
        return self.full_name or f"Profile for {self.user.email}"
