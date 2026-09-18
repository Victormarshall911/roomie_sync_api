# RoomieSync Backend Audit: Supabase to Django Migration Blueprint

> **CRITICAL MIGRATION NOTICE**
> The live Supabase project has been deleted — there is no dashboard or CLI access (`supabase db dump`, `supabase functions list`) to inspect live configurations. This audit was constructed from client-side source code analysis, repository SQL definitions (`supabase_schema.sql`), and commit history.
>
> Treat every inferred assumption (RLS policies, trigger side-effects, database constraints) as **unverified** and flag it for validation during development and manual testing. Every assumption and architectural decision is explicitly documented in the final checklist as:
> `reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.`

---

## Architecture & Infrastructure Overview

### 1. Client Initialization & Credentials
- **Client Configuration Location**: [`src/lib/supabase.ts:45`](file:///home/victor/Desktop/RoomieSync/src/lib/supabase.ts#L45)
- **Singleton Pattern**: Exactly one Supabase client instance is initialized and exported as `supabase`.
- **Environment Variables**:
  - `EXPO_PUBLIC_SUPABASE_URL`: Supabase project API gateway (found in [`.env:1`](file:///home/victor/Desktop/RoomieSync/.env#L1): `https://cvzylzcjluemwmorvyxv.supabase.co`).
  - `EXPO_PUBLIC_SUPABASE_ANON_KEY`: Supabase anon public JWT (found in [`.env:2`](file:///home/victor/Desktop/RoomieSync/.env#L2)).
  - `SUPABASE_SERVICE_ROLE_KEY`: Used only server-side within Supabase Edge Functions (`send-notification` & `notify-message`). Not exposed to the React Native client bundle.
- **Client Storage Engine**:
  - Native (`iOS` / `Android`): `@react-native-async-storage/async-storage` via a custom wrapper [`src/lib/supabase.ts:7-35`](file:///home/victor/Desktop/RoomieSync/src/lib/supabase.ts#L7-L35).
  - Web: Browser `localStorage`.
- **Auth Flags Configured**:
  - `autoRefreshToken: true`
  - `persistSession: true`
  - `detectSessionInUrl: false` (Magic links / OAuth URL redirections are explicitly disabled at the client init level).

### 2. Third-Party Telemetry & External Services Audit
An exhaustive scan was conducted across [`.env`](file:///home/victor/Desktop/RoomieSync/.env), [`app.json`](file:///home/victor/Desktop/RoomieSync/app.json), and [`package.json`](file:///home/victor/Desktop/RoomieSync/package.json) for third-party SDKs, tracking keys, crash reporting, or external API endpoints:
- **Crash Reporting / Error Tracking (Sentry, Bugsnag)**: **None found**.
- **Product Analytics (PostHog, Mixpanel, Segment, Firebase)**: **None found**.
- **Push Notification Providers (OneSignal, Pusher)**: **None found**.
- **In-App Purchases / Subscriptions (RevenueCat)**: **None found**.
- **Registered External Services**:
  1. **Supabase API Gateway**: `https://cvzylzcjluemwmorvyxv.supabase.co`
  2. **Expo Push Notification Service**: `https://exp.host/--/api/v2/push/send`
  3. **Expo Application Services (EAS)**: Project ID `862a937a-7518-472d-8e8a-e91b2c456789` (configured in [`app.json:32`](file:///home/victor/Desktop/RoomieSync/app.json#L32)).
  4. **Expo Font Loader**: Google Fonts (`@expo-google-fonts/inter`, `@expo-google-fonts/sora`).

---

## 1. Domain: Authentication & Session Management

### Schema & Data Models
In Supabase, user credentials and authentication were maintained in `auth.users`, and linked 1-to-1 with `public.profiles` where `profiles.id = auth.users.id`.

```sql
-- Reconstructed from supabase_schema.sql:4-27
CREATE TABLE profiles (
  id UUID REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
  full_name TEXT NOT NULL,
  university TEXT NOT NULL,
  department TEXT NOT NULL,
  gender TEXT CHECK (gender IN ('Male', 'Female', 'Non-binary', 'Prefer not to say')),
  budget_min INTEGER DEFAULT 0,
  budget_max INTEGER DEFAULT 300000,
  location_preference TEXT,
  sleep_habit TEXT CHECK (sleep_habit IN ('Night Owl', 'Early Bird')),
  cleanliness INTEGER CHECK (cleanliness >= 1 AND cleanliness <= 10),
  socializing TEXT CHECK (socializing IN ('Guests often', 'Rarely')),
  smoking TEXT CHECK (smoking IN ('Yes', 'No')),
  noise_level TEXT CHECK (noise_level IN ('Quiet', 'Moderate', 'Lively')),
  study_time TEXT CHECK (study_time IN ('Morning', 'Night', 'Varies')),
  drinking_habit TEXT CHECK (drinking_habit IN ('Often', 'Socially', 'Rarely/Never')),
  pets_preference TEXT CHECK (pets_preference IN ('Love them', 'Okay with them', 'Prefer no pets')),
  avatar_url TEXT,
  school_id_url TEXT,
  is_verified BOOLEAN DEFAULT FALSE,
  is_admin BOOLEAN DEFAULT FALSE,
  searching_for TEXT DEFAULT 'Looking for Roommate',
  push_token TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Operations & Queries

| Operation | Target / Method | Screen / Hook / Context | File & Line Number | Role / Permissions | Description & RLS Assumption |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Get Session** | `supabase.auth.getSession()` | `AuthProvider` mount | [`src/context/AuthContext.tsx:30`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L30) | Public / Any | Restores stored session on cold start. |
| **Auth Listener** | `supabase.auth.onAuthStateChange()` | `AuthProvider` lifecycle | [`src/context/AuthContext.tsx:37`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L37) | Public / Any | Listens for sign-in, token refresh, and sign-out events. |
| **Sign Up** | `supabase.auth.signUp({ email, password })` | `AuthScreen.handleAuth` | [`src/screens/AuthScreen.tsx:41`](file:///home/victor/Desktop/RoomieSync/src/screens/AuthScreen.tsx#L41) | Anonymous | Creates new account. Triggers Supabase confirmation email. |
| **Sign In** | `supabase.auth.signInWithPassword({ email, password })` | `AuthScreen.handleAuth` | [`src/screens/AuthScreen.tsx:45`](file:///home/victor/Desktop/RoomieSync/src/screens/AuthScreen.tsx#L45) | Anonymous | Returns access token, refresh token, and user session. |
| **Sign Out** | `supabase.auth.signOut()` | `AuthProvider.signOut` | [`src/context/AuthContext.tsx:98`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L98) | Authenticated | Clears Supabase JWT from AsyncStorage and unsets session state. |
| **Delete Account** | `supabase.from('profiles').delete().eq('id', user.id)` | `SettingsScreen.handleDeleteAccount` | [`src/screens/SettingsScreen.tsx:31-34`](file:///home/victor/Desktop/RoomieSync/src/screens/SettingsScreen.tsx#L31-L34) | Self (`auth.uid() = id`) | Deletes user profile record, followed by `signOut()`. RLS: `CREATE POLICY "Users can delete own profile" ON profiles FOR DELETE USING (auth.uid() = id);` |

### Auth Mechanics & Session Lifecycle
- **Tokens**: In Supabase, tokens are JWTs containing `sub` (User UUID) and `role: 'authenticated'`. Handled automatically by `@supabase/supabase-js`.
- **Custom Claims / Metadata**: No custom claims are set on `auth.users.user_metadata`. Administrative access is determined strictly via database column `profiles.is_admin` (`SELECT is_admin FROM profiles WHERE id = auth.uid()`).
- **OAuth / Deep Links**: No OAuth providers (`signInWithOAuth`) exist in the codebase. `detectSessionInUrl: false` confirms no deep link auth flow exists.
- **Offline Onboarding Staging**: When an unauthenticated student completes the onboarding quiz (`ProfileSetupScreen` -> `PreferencesScreen` -> `LifestyleSurveyScreen`), their profile answers are stored locally in `AsyncStorage` under `@pending_profile` ([`src/screens/LifestyleSurveyScreen.tsx:137`](file:///home/victor/Desktop/RoomieSync/src/screens/LifestyleSurveyScreen.tsx#L137)). Upon sign-in or sign-up, `AuthProvider.fetchProfile` reads `@pending_profile`, optionally uploads their local avatar, performs `supabase.from('profiles').upsert()`, and cleans up the key ([`src/context/AuthContext.tsx:53-69`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L53-L69)).

### Email Confirmation Flow: Behavior Gap Analysis & Decision

> [!IMPORTANT]
> **Behavior Gap**: In the current Supabase frontend, `supabase.auth.signUp()` automatically triggered Supabase's built-in email verification system, prompting the UI to display:
> `Alert.alert('Success', 'Check your email for the verification link!')` ([`src/screens/AuthScreen.tsx:43`](file:///home/victor/Desktop/RoomieSync/src/screens/AuthScreen.tsx#L43)).
> 
> In a Django + DRF migration, Supabase's invisible email dispatch disappears. This requires an explicit architectural decision:

1. **Option 1 (Recommended for Production)**: **Explicit Email Verification with OTP / HMAC Token**
   - Add `is_email_verified = models.BooleanField(default=False)` to the custom `User` model.
   - Upon `POST /api/v1/auth/register/`, generate a time-limited 6-digit numeric OTP or signed HMAC token stored in Redis/DB with 15-minute expiry.
   - Dispatch an asynchronous email via Celery task (`tasks.send_verification_email`) using SendGrid / Postmark / Amazon SES / SMTP.
   - Add endpoint `POST /api/v1/auth/verify-email/` (`{ "email": "...", "code": "123456" }`).
   - If unverified, `POST /api/v1/auth/token/` returns `403 Forbidden` (`{"detail": "Email not verified", "code": "email_unverified"}`).
2. **Option 2 (Alpha / Rapid Development Alternative)**: **Immediate Auto-Activation**
   - Set `User.is_active = True` immediately upon registration.
   - Skip email verification temporarily, allowing immediate sign-in, and rely solely on the student ID verification step (`is_verified` on `Profile`) for marketplace gating.
3. **Option 3**: **Institutional (.edu / .edu.ng) Domain Validation**
   - Restrict registration emails to approved Nigerian university domains (e.g. `@unilag.edu.ng`, `@ui.edu.ng`) paired with an activation email.

**Migration Decision**: Implement **Option 1** (Standard Email Token/OTP Verification) in Django with Celery. During local development, configure `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` to print verification codes directly to the terminal.

### Django Migration Architecture
- **Django App**: `accounts`
- **Model**: Custom `User` model extending `AbstractBaseUser` + `PermissionsMixin` with `id = models.UUIDField(primary_key=True, default=uuid.uuid4)`, `email = models.EmailField(unique=True)`, `is_email_verified = models.BooleanField(default=False)`.
- **Authentication Engine**: `djangorestframework-simplejwt` (JWT access & refresh tokens).
- **Endpoints**:
  - `POST /api/v1/auth/register/` -> Creates user and staged profile; triggers email verification code via Celery.
  - `POST /api/v1/auth/verify-email/` -> Validates 6-digit OTP; sets `is_email_verified = True`.
  - `POST /api/v1/auth/resend-code/` -> Re-sends activation code.
  - `POST /api/v1/auth/token/` -> Issues JWT pair (replaces `signInWithPassword`).
  - `POST /api/v1/auth/token/refresh/` -> Refreshes access token.
  - `POST /api/v1/auth/logout/` -> Blacklists refresh token.
  - `DELETE /api/v1/auth/me/` -> Deletes user account and cascades to profile, listings, and conversations.

---

## 2. Domain: Users & Profiles

### Schema & Data Models
The `profiles` table stores user details, academic info, roommate lifestyle habits, and roommate search state.

> [!WARNING]
> **Schema Cleanup: Deprecation of `has_room_info` (JSONB)**
> An exhaustive repository search (`grep -rn "has_room_info" src/`) confirmed that `has_room_info` appears in **only one place** in the entire codebase: an optional property on the TypeScript `Profile` interface in [`src/utils/matching.ts:24`](file:///home/victor/Desktop/RoomieSync/src/utils/matching.ts#L24).
> 
> Git history reveals it was added in commit `2b4d4d4` before the dedicated `listings` table was developed. **No screen, hook, or query reads from or writes to `has_room_info`.**
> 
> **Decision**: **DROP `has_room_info` from the Django `Profile` model.** Do not carry forward unused legacy schema debt.

```sql
-- Reconstructed Schema for profiles (dropping deprecated has_room_info)
TABLE public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    university TEXT NOT NULL,
    department TEXT NOT NULL,
    gender TEXT CHECK (gender IN ('Male', 'Female', 'Non-binary', 'Prefer not to say')),
    budget_min INTEGER DEFAULT 0,
    budget_max INTEGER DEFAULT 300000,
    location_preference TEXT,
    sleep_habit TEXT CHECK (sleep_habit IN ('Night Owl', 'Early Bird')),
    cleanliness INTEGER CHECK (cleanliness >= 1 AND cleanliness <= 10),
    socializing TEXT CHECK (socializing IN ('Guests often', 'Rarely')),
    smoking TEXT CHECK (smoking IN ('Yes', 'No')),
    noise_level TEXT CHECK (noise_level IN ('Quiet', 'Moderate', 'Lively')),
    study_time TEXT CHECK (study_time IN ('Morning', 'Night', 'Varies')),
    drinking_habit TEXT CHECK (drinking_habit IN ('Often', 'Socially', 'Rarely/Never')),
    pets_preference TEXT CHECK (pets_preference IN ('Love them', 'Okay with them', 'Prefer no pets')),
    avatar_url TEXT,
    school_id_url TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE,
    searching_for TEXT DEFAULT 'Looking for Roommate' CHECK (searching_for IN ('Looking for Roommate', 'Listing a Space', 'Already Matched')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Operations & Queries

| Operation | Target / Method | Screen / Hook / Context | File & Line Number | Role / Permissions | Description & Query Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fetch Current Profile** | `.from('profiles').select('*').eq('id', userId).single()` | `AuthProvider.fetchProfile` | [`src/context/AuthContext.tsx:71-75`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L71-L75) | Authenticated | Fetches authenticated user's own profile. RLS: `Public profiles are viewable by everyone` (USING true). |
| **Upsert Onboarding Profile** | `.from('profiles').upsert({ id: userId, ...pendingProfile })` | `AuthProvider.fetchProfile` | [`src/context/AuthContext.tsx:67`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L67) | Self (`auth.uid() = id`) | Flushes pending onboarding data saved during pre-auth steps. |
| **Upsert Survey Data** | `.from('profiles').upsert({ id: user.id, ...fullProfileToSave })` | `LifestyleSurveyScreen.handleSubmit` | [`src/screens/LifestyleSurveyScreen.tsx:148-151`](file:///home/victor/Desktop/RoomieSync/src/screens/LifestyleSurveyScreen.tsx#L148-L151) | Self (`auth.uid() = id`) | Saves all lifestyle questions and basic bio after survey completion. |
| **Update Profile Details** | `.from('profiles').update({...fields}).eq('id', user.id)` | `EditProfileScreen.handleSave` | [`src/screens/EditProfileScreen.tsx:95-115`](file:///home/victor/Desktop/RoomieSync/src/screens/EditProfileScreen.tsx#L95-L115) | Self (`auth.uid() = id`) | Updates name, university, department, gender, budget, lifestyle, location, and avatar. |
| **Toggle Search Status** | `.from('profiles').update({ searching_for: status }).eq('id', user.id)` | `ProfileScreen.updateStatus` | [`src/screens/ProfileScreen.tsx:52-55`](file:///home/victor/Desktop/RoomieSync/src/screens/ProfileScreen.tsx#L52-L55) | Self (`auth.uid() = id`) | Switches between `'Looking for Roommate'`, `'Listing a Space'`, and `'Already Matched'`. |
| **Fetch Recipient Profile** | `.from('profiles').select('*').eq('id', otherUser.id).single()` | `ChatScreen` mount | [`src/screens/ChatScreen.tsx:97-101`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L97-L101) | Authenticated | Fetches active chat partner's profile to obtain fresh `is_verified` and name. |
| **Read Block List** | `.from('blocks').select('blocked_id').eq('blocker_id', userId)` | `AuthProvider.fetchProfile` | [`src/context/AuthContext.tsx:81`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L81) | Self (`blocker_id = auth.uid()`) | Loads IDs of blocked users into context state. |

### RLS Policies Identified from SQL
```sql
CREATE POLICY "Public profiles are viewable by everyone" ON profiles FOR SELECT USING (true);
CREATE POLICY "Users can insert their own profile" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "Users can update their own profile" ON profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can delete own profile" ON profiles FOR DELETE USING (auth.uid() = id);
```

### Django Migration Architecture
- **Django App**: `profiles`
- **Django Model**: `Profile` (OneToOneField with `User`, `primary_key=True`).
- **Fields**:
  - `full_name` (`CharField(max_length=255)`)
  - `university` (`CharField(max_length=255)`)
  - `department` (`CharField(max_length=255)`)
  - `gender` (`CharField(choices=['Male', 'Female', 'Non-binary', 'Prefer not to say'])`)
  - `budget_min`, `budget_max` (`PositiveIntegerField(default=0)`)
  - `location_preference` (`CharField(max_length=255, blank=True)`)
  - `sleep_habit` (`CharField(choices=['Night Owl', 'Early Bird'])`)
  - `cleanliness` (`PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])`)
  - `socializing` (`CharField(choices=['Guests often', 'Rarely'])`)
  - `smoking` (`CharField(choices=['Yes', 'No'])`)
  - `noise_level` (`CharField(choices=['Quiet', 'Moderate', 'Lively'])`)
  - `study_time` (`CharField(choices=['Morning', 'Night', 'Varies'])`)
  - `drinking_habit` (`CharField(choices=['Often', 'Socially', 'Rarely/Never'])`)
  - `pets_preference` (`CharField(choices=['Love them', 'Okay with them', 'Prefer no pets'])`)
  - `avatar` (`ImageField(upload_to='avatars/%Y/%m/', null=True, blank=True)`)
  - `is_verified` (`BooleanField(default=False)`)
  - `is_admin` (`BooleanField(default=False)`)
  - `searching_for` (`CharField(choices=['Looking for Roommate', 'Listing a Space', 'Already Matched'], default='Looking for Roommate')`)
- **DRF Endpoints**:
  - `GET /api/v1/profiles/me/` -> Current user profile.
  - `PATCH /api/v1/profiles/me/` -> Partial update (bio, lifestyle, search status).
  - `GET /api/v1/profiles/<uuid:pk>/` -> Public profile details.

---

## 3. Domain: Listings

### Schema & Data Models

> [!WARNING]
> **Architecture Decision: Dropping Development Scaffolding (`creator_name_demo` & 85% Mock Fallback)**
> In `consolidated_setup.sql`, demo items were seeded with `user_id = NULL` and `creator_name_demo = 'Chidi Okechukwu'`. To handle these unattached cards in the frontend, [`src/screens/DiscoveryScreen.tsx:223`](file:///home/victor/Desktop/RoomieSync/src/screens/DiscoveryScreen.tsx#L223) contains the following fallback:
> `const matchPct = (profile && item.profiles) ? calculateMatchPercentage(profile as Profile, item.profiles) : (item.user_id ? 0 : 85);`
> 
> **Decision**: In production Django, **DROP `creator_name_demo` completely**. Require every listing to have a non-nullable foreign key to a real `User` (`user_id = ForeignKey(User, on_delete=CASCADE, null=False)`). The client will compute or receive real match scores for all cards without fake 85% mock fallbacks.

```sql
-- Production Reconstructed Schema for listings (dropping creator_name_demo)
TABLE public.listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    price INTEGER,
    location TEXT,
    type TEXT CHECK (type IN ('Room', 'Roommate')),
    searching_for TEXT CHECK (searching_for IN ('Looking for Roommate', 'Listing a Space')),
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Operations & Queries

| Operation | Target / Method | Screen / Hook | File & Line Number | Role / Permissions | Description & Query Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Discovery Feed (Paginated)** | `.from('listings').select('*, profiles(*)').eq('is_available', true).range(from, to).order('created_at', { ascending: false })` | `DiscoveryScreen.fetchListings` | [`src/screens/DiscoveryScreen.tsx:147-151`](file:///home/victor/Desktop/RoomieSync/src/screens/DiscoveryScreen.tsx#L147-L151) | Public / Any | Paginated list (20 items/page). Joins creator's `profiles`. Optional filter `.eq('searching_for', filterStatus)` ([`line 154`](file:///home/victor/Desktop/RoomieSync/src/screens/DiscoveryScreen.tsx#L154)). |
| **My Listings** | `.from('listings').select('*, profiles(*)').eq('user_id', user.id).order('created_at', { ascending: false })` | `ProfileScreen.fetchMyListings` | [`src/screens/ProfileScreen.tsx:25-29`](file:///home/victor/Desktop/RoomieSync/src/screens/ProfileScreen.tsx#L25-L29) | Owner (`user_id = auth.uid()`) | Fetches all listings posted by the current user. |
| **Create Listing** | `.from('listings').insert(insertPayload)` | `CreateListingScreen.handleSubmit` | [`src/screens/CreateListingScreen.tsx:31-32`](file:///home/victor/Desktop/RoomieSync/src/screens/CreateListingScreen.tsx#L31-L32) | Authenticated & Verified | Inserts new listing. Note client checks `profile.is_verified` before opening screen ([`DiscoveryScreen.tsx:199`](file:///home/victor/Desktop/RoomieSync/src/screens/DiscoveryScreen.tsx#L199)). Fallback retry without `images` if column is missing ([`line 39`](file:///home/victor/Desktop/RoomieSync/src/screens/CreateListingScreen.tsx#L39)). |
| **Update Listing** | `.from('listings').update(updatePayload).eq('id', listing.id)` | `EditListingScreen.handleSubmit` | [`src/screens/EditListingScreen.tsx:40-42`](file:///home/victor/Desktop/RoomieSync/src/screens/EditListingScreen.tsx#L40-L42) | Owner (`user_id = auth.uid()`) | Updates title, price, location, description, type, searching_for, images. |
| **Toggle Availability** | `.from('listings').update({ is_available: newStatus }).eq('id', listing.id)` | `ListingDetailScreen.toggleAvailability` | [`src/screens/ListingDetailScreen.tsx:82`](file:///home/victor/Desktop/RoomieSync/src/screens/ListingDetailScreen.tsx#L82) | Owner (`user_id = auth.uid()`) | Toggles listing status between Available and Taken. |
| **Delete Listing** | `.from('listings').delete().eq('id', listing.id)` | `ListingDetailScreen` (delete dialog) | [`src/screens/ListingDetailScreen.tsx:209-212`](file:///home/victor/Desktop/RoomieSync/src/screens/ListingDetailScreen.tsx#L209-L212) | Owner (`user_id = auth.uid()`) | Permanently removes listing. |

### RLS Policies Identified from SQL
```sql
CREATE POLICY "Listings are viewable by everyone" ON listings FOR SELECT USING (true);
CREATE POLICY "Users can create their own listings" ON listings FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own listings" ON listings FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own listings" ON listings FOR DELETE USING (auth.uid() = user_id);
```

### Django Migration Architecture
- **Django App**: `listings`
- **Django Models**:
  - `Listing`: `user` (FK to `User`, `related_name='listings'`), `title`, `description`, `price` (PositiveIntegerField), `location`, `type` (choices `Room`, `Roommate`), `searching_for` (choices `Looking for Roommate`, `Listing a Space`), `is_available` (BooleanField, default True), timestamps.
  - `ListingImage`: `listing` (FK to `Listing`, `related_name='images'`), `image` (`ImageField(upload_to='listings/%Y/%m/')`), `order` (PositiveIntegerField, default=0). *Migrating from loose string arrays to a relational image model enables real multi-part file uploads, ordering, and S3 file cleanup.*
- **DRF Endpoints & Permissions**:
  - `GET /api/v1/listings/` -> `ListAPIView` with pagination (`PageNumberPagination`, page_size=20), filtering (`django-filter` on `searching_for`, search on `title`, `location`, `user__full_name`).
  - `POST /api/v1/listings/` -> `CreateAPIView` (Requires `IsAuthenticated` and `IsVerifiedStudent`).
  - `GET /api/v1/listings/<uuid:pk>/` -> `RetrieveAPIView`.
  - `PATCH /api/v1/listings/<uuid:pk>/` -> `UpdateAPIView` (Requires `IsOwner`).
  - `DELETE /api/v1/listings/<uuid:pk>/` -> `DestroyAPIView` (Requires `IsOwner`).
  - `POST /api/v1/listings/<uuid:pk>/toggle-availability/` -> Custom action toggling `is_available`.

---

## 4. Domain: Matching Algorithm

### Overview
In the current Supabase architecture, matching calculations are executed **entirely client-side** via [`src/utils/matching.ts`](file:///home/victor/Desktop/RoomieSync/src/utils/matching.ts). The frontend downloads complete profile payloads during discovery (`listings.select('*, profiles(*)')`) and calculates compatibility scores in memory against the viewer's profile.

### Scoring Logic & Weights
Source: [`src/utils/matching.ts:31-142`](file:///home/victor/Desktop/RoomieSync/src/utils/matching.ts#L31-L142)

| Factor | Weight | Evaluation Criteria |
| :--- | :--- | :--- |
| **Budget Overlap** | **25%** | Overlap ratio between `[p1.min, p1.max]` and `[p2.min, p2.max]`. If `maxMin <= minMax`, ratio is `(overlapRange * 2) / (range1 + range2)`. |
| **Location Preference** | **15%** | 100% score for exact string match (case-insensitive); 70% partial match for substring containment. |
| **Cleanliness** | **12%** | Scaled 1 to 10 (stored as 3, 6, 9). Exact match = 100%; difference $\le 3$ scores $1 - (\Delta / 6)$. |
| **Sleep Habit** | **10%** | Binary match (`'Early Bird'` vs `'Night Owl'`). |
| **Noise Level** | **10%** | Exact match (`'Quiet'`, `'Moderate'`, `'Lively'`). |
| **Socializing** | **8%** | Exact match (`'Guests often'` vs `'Rarely'`). |
| **Study Time** | **8%** | Exact match (`'Morning'`, `'Night'`, `'Varies'`). |
| **Smoking** | **6%** | Exact match (`'Yes'` vs `'No'`). |
| **Drinking** | **6%** | Exact match (`'Often'`, `'Socially'`, `'Rarely/Never'`). |
| **Default Fallback** | — | If no common attributes exist, returns 50% baseline. |

### Django Migration Architecture
- **Django App**: `matching`
- **Implementation Strategy**:
  - Implement the matching algorithm as a pure Python domain service: `matching/services.py:calculate_match(profile_a, profile_b)`.
  - Serializer integration: In `ListingSerializer` and `ProfileSerializer`, calculate and attach `match_percentage = serializers.SerializerMethodField()` when `request.user` is authenticated.
  - REST endpoint: `GET /api/v1/matches/` returning sorted roommate recommendations.
  - Performance optimization: Cache match scores in Redis (`cache.set(f"match:{uid_a}:{uid_b}", score, timeout=86400)`) and invalidate on profile updates.

---

## 5. Domain: Chat & Realtime Messaging

### Schema & Data Models
Two tables power direct 1-on-1 messaging: `conversations` (DM threads) and `messages`.

```sql
-- Reconstructed from supabase_schema.sql:29-45
CREATE TABLE public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user1_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    user2_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user1_id, user2_id)
);

CREATE TABLE public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Operations & Queries

| Operation | Target / Method | Screen / Hook / Context | File & Line Number | Role / Permissions | Description & Query Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Find Existing Convo** | `.from('conversations').select('id, user1_id, user2_id').or('user1_id.eq.${uid},user2_id.eq.${uid}')` | `ListingDetailScreen.handleChat`, `UserProfileScreen.handleChat` | [`src/screens/ListingDetailScreen.tsx:50-53`](file:///home/victor/Desktop/RoomieSync/src/screens/ListingDetailScreen.tsx#L50-L53), [`src/screens/UserProfileScreen.tsx:36-39`](file:///home/victor/Desktop/RoomieSync/src/screens/UserProfileScreen.tsx#L36-L39) | Authenticated | Finds if a thread already exists between viewer and lister. Filtered in JS to avoid `PGRST116` errors. |
| **Fetch Inbox Conversations** | `.from('conversations').select('*, profiles!user1_id(*), user2:profiles!user2_id(*), messages(content, created_at, sender_id)').or(...).order('created_at', { ascending: false, foreignTable: 'messages' })` | `ConversationsScreen.fetchConversations` | [`src/screens/ConversationsScreen.tsx:51-59`](file:///home/victor/Desktop/RoomieSync/src/screens/ConversationsScreen.tsx#L51-L59) | Member of conversation | Loads all conversations with partner profile join and nested messages. Filtered in JS for blocked users and sorted by latest message date. |
| **Unread Count Check** | `.from('conversations').select('id, messages(sender_id, created_at)').or(...).order(...).limit(1, { foreignTable: 'messages' })` | `MessageContext.refreshUnreadCount` | [`src/context/MessageContext.tsx:30-38`](file:///home/victor/Desktop/RoomieSync/src/context/MessageContext.tsx#L30-L38) | Member of conversation | Reads the latest message for every conversation, compares against `AsyncStorage` `last_read_${convId}` to count unread threads. |
| **Fetch Message History** | `.from('messages').select('*').eq('conversation_id', activeConversationId).order('created_at', { ascending: true })` | `ChatScreen.fetchMessages` | [`src/screens/ChatScreen.tsx:201-205`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L201-L205) | Conversation participant | Retrieves all messages in ascending order for the active conversation. |
| **Create Conversation** | `.from('conversations').insert({ user1_id: user.id, user2_id: otherUser.id }).select().single()` | `ChatScreen.sendMessage` (late init) | [`src/screens/ChatScreen.tsx:229-233`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L229-L233) | Authenticated | Late-initializes a conversation upon sending the first message. |
| **Send Message** | `.from('messages').insert({ conversation_id: convId, sender_id: user.id, content: msg }).select().single()` | `ChatScreen.sendMessage` | [`src/screens/ChatScreen.tsx:245-252`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L245-L252) | Authenticated sender | Inserts message. Returns newly created record. |

### Realtime Channels & Subscriptions
1. **Global Unread Counter Subscription**:
   - Channel: `'global-messages'` ([`src/context/MessageContext.tsx:73`](file:///home/victor/Desktop/RoomieSync/src/context/MessageContext.tsx#L73))
   - Event: `INSERT` on `public.messages`
   - Trigger: Calls `refreshUnreadCount()` if `payload.new.sender_id !== user.id`.
   - Teardown: `supabase.removeChannel(channel)` in `useEffect` cleanup ([`line 88`](file:///home/victor/Desktop/RoomieSync/src/context/MessageContext.tsx#L88)).
2. **Conversations List Screen Subscription**:
   - Channel: `'conversations-list'` ([`src/screens/ConversationsScreen.tsx:97`](file:///home/victor/Desktop/RoomieSync/src/screens/ConversationsScreen.tsx#L97))
   - Event: `INSERT` on `public.messages`
   - Trigger: Calls `fetchConversations(false)` to update previews and time order.
   - Teardown: `supabase.removeChannel(channel)` in `useEffect` cleanup ([`line 109`](file:///home/victor/Desktop/RoomieSync/src/screens/ConversationsScreen.tsx#L109)).
3. **Active Chat Room Subscription**:
   - Channel: `room:${activeConversationId}:${Date.now()}` ([`src/screens/ChatScreen.tsx:169`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L169))
   - Event: `INSERT` on `public.messages` with filter `conversation_id=eq.${activeConversationId}`
   - Trigger: Appends `payload.new` to message list, calls `markAsRead()`, auto-scrolls to bottom if near bottom.
   - Teardown: `supabase.removeChannel(channel)` in `useEffect` cleanup ([`line 195`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L195)).

### RLS Policies Identified from SQL
```sql
CREATE POLICY "Users can see conversations they are part of" ON conversations FOR SELECT 
USING (auth.uid() = user1_id OR auth.uid() = user2_id);

CREATE POLICY "Users can create conversations" ON conversations FOR INSERT 
WITH CHECK (auth.uid() = user1_id OR auth.uid() = user2_id);

CREATE POLICY "Users can see messages in their conversations" ON messages FOR SELECT 
USING (EXISTS (SELECT 1 FROM conversations WHERE conversations.id = messages.conversation_id AND (conversations.user1_id = auth.uid() OR conversations.user2_id = auth.uid())));

CREATE POLICY "Users can send messages in their conversations" ON messages FOR INSERT 
WITH CHECK (auth.uid() = sender_id AND EXISTS (SELECT 1 FROM conversations WHERE conversations.id = messages.conversation_id AND (conversations.user1_id = auth.uid() OR conversations.user2_id = auth.uid())));
```

### Django Migration Architecture
- **Django App**: `chat`
- **Django Models**:
  - `Conversation`: `id` (UUID PK), `user1` (FK to User), `user2` (FK to User), `created_at`.
    - **Canonical Ordering Fix**: In `save()`, always enforce `user1_id = min(u1_id, u2_id)` and `user2_id = max(u1_id, u2_id)` to guarantee true bi-directional uniqueness without duplicate conversation threads.
  - `Message`: `id` (UUID PK), `conversation` (FK to Conversation), `sender` (FK to User), `content` (TextField), `created_at`, `is_read` (BooleanField, default False - *adds true server-side read receipts instead of volatile client AsyncStorage*).
- **REST Endpoints**:
  - `GET /api/v1/chat/conversations/` -> Inbox list with partner profile, last message, and unread count.
  - `POST /api/v1/chat/conversations/` -> Start or retrieve existing conversation with target user.
  - `GET /api/v1/chat/conversations/<uuid:id>/messages/` -> Message history with pagination (`CursorPagination` on `created_at`).
  - `POST /api/v1/chat/conversations/<uuid:id>/messages/` -> Send message fallback.
  - `POST /api/v1/chat/conversations/<uuid:id>/read/` -> Mark all unread messages as read.
- **WebSockets / Realtime Architecture**:
  - **Django Channels** + **Redis Channel Layer** (`channels_redis`).
  - WebSocket Consumer: `ChatConsumer(AsyncJsonWebsocketConsumer)` mounted at `ws/chat/<uuid:conversation_id>/`.
  - Authenticates via JWT token passed in query parameter or headers.
  - Channel Layer Groups:
    - `chat_{conversation_id}`: Delivers new chat messages in real time to both participants.
    - `user_{user_id}`: Delivers global unread count badge increments and inbox updates.

---

## 6. Domain: Moderation (Reports & Blocks)

### Schema & Data Models
Two tables handle safety, reporting malicious users/listings, and blocking unwanted users.

```sql
-- Reconstructed from supabase_schema.sql:169-185
CREATE TABLE public.reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    reported_user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    listing_id UUID REFERENCES listings(id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    blocked_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(blocker_id, blocked_id)
);
```

### Operations & Queries

| Operation | Target / Method | Screen / Hook / Context | File & Line Number | Role / Permissions | Description & Query Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fetch Block List** | `.from('blocks').select('blocked_id').eq('blocker_id', userId)` | `AuthProvider.fetchProfile` | [`src/context/AuthContext.tsx:81`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L81) | Authenticated Self | Loads array of blocked user IDs to filter listings and chats. |
| **Block User** | `.from('blocks').insert({ blocker_id: user.id, blocked_id: blockedId })` | `AuthProvider.blockUser` | [`src/context/AuthContext.tsx:105`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L105) | Authenticated Self | Triggered from `ListingDetailScreen.handleBlock`, `UserProfileScreen.handleBlock`, `ChatScreen.handleBlock`. |
| **Report Listing** | `.from('reports').insert({ reporter_id, reported_user_id, listing_id, reason })` | `ListingDetailScreen.submitReport` | [`src/screens/ListingDetailScreen.tsx:104-109`](file:///home/victor/Desktop/RoomieSync/src/screens/ListingDetailScreen.tsx#L104-L109) | Authenticated | Submits safety report against a listing and its owner. Reasons: `'Inappropriate Content'`, `'Scam or Spam'`. |
| **Report Profile** | `.from('reports').insert({ reporter_id, reported_user_id, reason })` | `UserProfileScreen.submitReport`, `ChatScreen.submitReport` | [`src/screens/UserProfileScreen.tsx:76-80`](file:///home/victor/Desktop/RoomieSync/src/screens/UserProfileScreen.tsx#L76-L80), [`src/screens/ChatScreen.tsx:134-138`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L134-L138) | Authenticated | Submits report directly against a student profile. |

### RLS Policies Identified from SQL
```sql
CREATE POLICY "Users can create reports" ON reports FOR INSERT WITH CHECK (auth.uid() = reporter_id);
CREATE POLICY "Users can view their own reports" ON reports FOR SELECT USING (auth.uid() = reporter_id);
CREATE POLICY "Admins can view all reports" ON reports FOR SELECT USING ((SELECT is_admin FROM profiles WHERE id = auth.uid()) = TRUE);

CREATE POLICY "Users can create blocks" ON blocks FOR INSERT WITH CHECK (auth.uid() = blocker_id);
CREATE POLICY "Users can view their own blocks" ON blocks FOR SELECT USING (auth.uid() = blocker_id);
CREATE POLICY "Users can delete their own blocks" ON blocks FOR DELETE USING (auth.uid() = blocker_id);
```

### Django Migration Architecture
- **Django App**: `moderation`
- **Django Models**:
  - `Report`: `reporter` (FK User), `reported_user` (FK User), `listing` (FK Listing, null=True, on_delete=SET_NULL), `reason` (TextField), `status` (choices `pending`, `investigating`, `resolved`, `dismissed`), `created_at`.
  - `Block`: `blocker` (FK User), `blocked` (FK User), `created_at`. Unique constraint on `('blocker', 'blocked')`.
- **DRF Endpoints**:
  - `POST /api/v1/moderation/reports/` -> Create safety report.
  - `GET /api/v1/moderation/blocks/` -> Get list of blocked user IDs.
  - `POST /api/v1/moderation/blocks/` -> Block a user (`{ "blocked_id": "<uuid>" }`).
  - `DELETE /api/v1/moderation/blocks/<uuid:blocked_id>/` -> Unblock.
- **Backend Queryset Filter Mixin**:
  - Provide a reusable `BlockedUsersFilterMixin` across listings and conversation querysets:
    `queryset.exclude(user__in=Block.objects.filter(blocker=request.user).values('blocked'))`

---

## 7. Domain: Student Verification

### Schema & Data Models
Student verification requires students to upload their school admission letter or student ID document to a private storage bucket (`student-ids`). Once reviewed by an administrator, `profiles.is_verified` is toggled to `TRUE`.

- Fields involved on `profiles`:
  - `school_id_url`: File path pointing into the `student-ids` bucket (e.g. `${user.id}/letter.jpg`).
  - `is_verified`: Boolean flag gating features like creating listings.

### Operations & Queries

| Operation | Target / Method | Screen / Hook | File & Line Number | Role / Permissions | Description & Query Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Upload ID Document** | `supabase.storage.from('student-ids').upload(filePath, arrayBuffer, { upsert: true, contentType })` | `VerificationScreen.uploadId` | [`src/screens/VerificationScreen.tsx:59-64`](file:///home/victor/Desktop/RoomieSync/src/screens/VerificationScreen.tsx#L59-L64) | Authenticated Self | Uploads ID image or PDF into private bucket `student-ids` under path `${user.id}/letter.${ext}`. |
| **Attach Document to Profile** | `supabase.from('profiles').update({ school_id_url: filePath }).eq('id', user.id)` | `VerificationScreen.uploadId` | [`src/screens/VerificationScreen.tsx:68-71`](file:///home/victor/Desktop/RoomieSync/src/screens/VerificationScreen.tsx#L68-L71) | Self (`auth.uid() = id`) | Links the storage path onto the user profile and triggers profile refetch. |

### Django Migration Architecture
- **Django App**: `verification`
- **Django Models**:
  - `VerificationRequest`: `user` (OneToOneField User), `document` (`FileField(upload_to='verification_documents/%Y/')`), `status` (choices `pending`, `approved`, `rejected`), `rejection_reason` (TextField, blank=True), `reviewed_by` (FK User, null=True), `submitted_at`, `reviewed_at`.
- **DRF Endpoints**:
  - `GET /api/v1/verification/status/` -> Returns verification status.
  - `POST /api/v1/verification/submit/` -> Multipart file upload for admission letter / student ID.

---

## 8. Domain: Admin Management

### Schema & Data Models
Administrative privileges are controlled by the `is_admin` boolean flag on the `profiles` table.

```sql
-- Storage Policy: Allow admins to view all objects in student-ids bucket (supabase_schema.sql:124-130)
CREATE POLICY "Admins can view all student-ids" ON storage.objects FOR SELECT TO authenticated
USING (
  bucket_id = 'student-ids' AND
  (SELECT is_admin FROM profiles WHERE id = auth.uid()) = TRUE
);

-- Profile Policy: Allow admins to update anyone's verification status (supabase_schema.sql:133-141)
CREATE POLICY "Admins can verify profiles" ON profiles FOR UPDATE TO authenticated
USING ((SELECT is_admin FROM profiles WHERE id = auth.uid()) = TRUE)
WITH CHECK ((SELECT is_admin FROM profiles WHERE id = auth.uid()) = TRUE);
```

### Operations & Queries

| Operation | Target / Method | Screen / Hook | File & Line Number | Role / Permissions | Description & Query Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Admin Tab Visibility** | `{profile?.is_admin && <Tab.Screen name="Admin" ... />}` | `MainTabs` | [`src/navigation/MainTabs.tsx:120-126`](file:///home/victor/Desktop/RoomieSync/src/navigation/MainTabs.tsx#L120-L126) | Admin only | Hides the Admin tab in the bottom bar unless `profile.is_admin === true`. |
| **List Pending Verifications** | `supabase.from('profiles').select('*').eq('is_verified', false).not('school_id_url', 'is', null)` | `AdminScreen.fetchUnverified` | [`src/screens/AdminScreen.tsx:23-28`](file:///home/victor/Desktop/RoomieSync/src/screens/AdminScreen.tsx#L23-L28) | Admin only | Queries all profiles with unverified status where a school ID document exists. |
| **Generate Signed URL** | `supabase.storage.from('student-ids').createSignedUrl(item.school_id_url, 60)` | `AdminScreen.VerificationCard` | [`src/screens/AdminScreen.tsx:104-107`](file:///home/victor/Desktop/RoomieSync/src/screens/AdminScreen.tsx#L104-L107) | Admin only | Requests temporary signed URL to preview private ID photo. **CRITICAL BUG IDENTIFIED**: Expiry time of 60 seconds is too short, causing images to fail loading if viewing for over a minute. |
| **Approve & Verify Student** | `supabase.from('profiles').update({ is_verified: true }).eq('id', userId)` | `AdminScreen.handleVerify` | [`src/screens/AdminScreen.tsx:40-44`](file:///home/victor/Desktop/RoomieSync/src/screens/AdminScreen.tsx#L40-L44) | Admin only | Sets `is_verified = true` on target student's profile. |

### Django Migration Architecture
- **Django App**: `admin_management` (and standard `django.contrib.admin`)
- **Permissions**: `rest_framework.permissions.IsAdminUser` (`request.user.is_staff` or `profile.is_admin`).
- **DRF Endpoints**:
  - `GET /api/v1/admin/verifications/` -> Lists pending student verifications.
  - `POST /api/v1/admin/verifications/<uuid:user_id>/approve/` -> Sets `is_verified = True` on Profile and sends push notification.
  - `POST /api/v1/admin/verifications/<uuid:user_id>/reject/` -> Sets status to rejected with reason feedback.
  - Signed URL view / protected media view: `GET /api/v1/admin/verifications/<uuid:user_id>/document/` -> Streams protected media or issues an S3 pre-signed URL with reasonable expiry (e.g. 30-60 minutes, fixing the 60-second client bug).

---

## 9. Domain: Notifications & Background Tasks

### Architecture Overview
Push notifications in RoomieSync are powered by the **Expo Push API** (`https://exp.host/--/api/v2/push/send`).

Two edge functions were written during development: `notify-message` and `send-notification`.

---

### Comparison of the Two Edge Functions in the Codebase

#### Function 1: `send-notification` (LIVE FUNCTION)
Source: [`supabase/functions/send-notification/index.ts`](file:///home/victor/Desktop/RoomieSync/supabase/functions/send-notification/index.ts)
```ts
// @ts-ignore
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
// @ts-ignore
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

const EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

// @ts-ignore
serve(async (req: any) => {
  try {
    const payload = await req.json()
    const { record } = payload
    
    // 1. Initialize Supabase client
    const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    const supabase = createClient(supabaseUrl, supabaseKey)

    // 2. Get the conversation to find the recipient
    const { data: conversation, error: convoError } = await supabase
      .from('conversations')
      .select('user1_id, user2_id')
      .eq('id', record.conversation_id)
      .single()

    if (convoError || !conversation) {
      return new Response(JSON.stringify({ error: 'Conversation not found' }), { status: 404 })
    }

    // 3. Determine recipient ID (the one who isn't the sender)
    const recipientId = record.sender_id === conversation.user1_id 
      ? conversation.user2_id 
      : conversation.user1_id

    // 4. Get recipient's push token and name of sender
    const [recipientRes, senderRes] = await Promise.all([
      supabase.from('profiles').select('push_token, full_name').eq('id', recipientId).single(),
      supabase.from('profiles').select('full_name').eq('id', record.sender_id).single()
    ])

    const pushToken = recipientRes.data?.push_token
    const senderName = senderRes.data?.full_name || 'Someone'

    if (!pushToken) {
      return new Response(JSON.stringify({ message: 'No push token for recipient' }), { status: 200 })
    }

    // 5. Send notification to Expo
    const message = {
      to: pushToken,
      sound: 'default',
      title: `New message from ${senderName}`,
      body: record.content,
      data: { 
        type: 'chat',
        conversationId: record.conversation_id,
        senderId: record.sender_id
      },
    }

    const res = await fetch(EXPO_PUSH_URL, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Accept-encoding': 'gzip, deflate',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(message),
    })

    const result = await res.json()
    return new Response(JSON.stringify(result), { 
      headers: { "Content-Type": "application/json" },
      status: 200 
    })

  } catch (error) {
    const err = error as Error;
    return new Response(JSON.stringify({ error: err.message }), { 
      headers: { "Content-Type": "application/json" },
      status: 500 
    })
  }
})
```

#### Function 2: `notify-message` (ABANDONED PROTOTYPE)
Source: [`supabase/functions/notify-message/index.ts`](file:///home/victor/Desktop/RoomieSync/supabase/functions/notify-message/index.ts)
```ts
// @ts-nocheck — Deno runtime; these imports resolve at deploy time
import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

serve(async (req: Request) => {
    try {
        const payload = await req.json()
        const { record } = payload

        if (!record || !record.conversation_id || !record.sender_id || !record.content) {
            return new Response(JSON.stringify({ error: 'Invalid payload' }), { status: 400 })
        }

        const supabase = createClient(
            Deno.env.get('SUPABASE_URL') ?? '',
            Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
        )

        const { data: conversation } = await supabase
            .from('conversations')
            .select('user1_id, user2_id')
            .eq('id', record.conversation_id)
            .single()

        const recipientId = record.sender_id === conversation.user1_id
            ? conversation.user2_id
            : conversation.user1_id

        const { data: profile } = await supabase
            .from('profiles')
            .select('push_token, full_name')
            .eq('id', recipientId)
            .single()

        if (!profile?.push_token) {
            return new Response(JSON.stringify({ message: 'No push token found' }), { status: 200 })
        }

        // Send notification via Expo
        const response = await fetch('https://exp.host/--/api/v2/push/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                to: profile.push_token,
                title: 'New Message', // Generic title (sender name omitted)
                body: record.content.length > 50 ? record.content.substring(0, 47) + '...' : record.content,
                data: { conversationId: record.conversation_id }, // Missing 'type' and 'senderId'
            }),
        })

        const result = await response.json()
        return new Response(JSON.stringify(result), { status: 200 })
    } catch (error: any) {
        return new Response(JSON.stringify({ error: error.message }), { status: 500 })
    }
})
```

---

### Technical Proof: Which Function Was Live?

Git commit logs and client code cross-referencing provide **definitive proof that `send-notification` was the active live function**:

1. **Commit Chronology**:
   - Commit `0c6a357` (Apr 21): `notify-message` was created initially.
   - Commit `1db717d` (May 8): `send-notification` was created as a brand new replacement.
   - Commit `f555198` (May 8): `send-notification` had type casting and error handling polished.
2. **Database Trigger Target**:
   In `supabase/enable_notifications.sql` (commit `04dcea6~1`), the database trigger calls:
   ```sql
   url := 'https://cvzylzcjluemwmorvyxv.supabase.co/functions/v1/send-notification'
   ```
   The trigger strictly calls `send-notification`, not `notify-message`.
3. **Client Click Handler Compatibility**:
   In [`src/hooks/useNotifications.ts:88-93`](file:///home/victor/Desktop/RoomieSync/src/hooks/useNotifications.ts#L88-L93):
   ```ts
   if (data?.type === 'chat' && data?.conversationId) {
       navigation.navigate('Chat', { 
           conversationId: data.conversationId,
           otherUser: data.otherUser || { id: data.senderId, full_name: 'User' }
       });
   }
   ```
   - `send-notification` sends `data: { type: 'chat', conversationId, senderId }` and personalized title `New message from ${senderName}`.
   - `notify-message` sent `data: { conversationId }` without `type` or `senderId`. Under `notify-message`, tapping a notification in the client would **fail silently** because `data?.type === 'chat'` would evaluate to `false`.

**Conclusion**: **`send-notification` was the live production function.** The older `notify-message` was an abandoned initial prototype. **Only port the `send-notification` logic into Django Celery.**

---

### Push Token Architecture Decision: 1:1 (`profiles.push_token`) vs Many:1 (`DeviceToken` Table)

In the Supabase schema, push tokens were stored as a single column: `profiles.push_token TEXT`.

- **Current Limitation**: When a user logs in on a second device or reinstalls the app, their previous push token is overwritten. The first device stops receiving notifications.
- **Migration Enhancement**:
  - Introduce a dedicated `DeviceToken` model in Django:
    ```python
    class DeviceToken(models.Model):
        user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_tokens')
        token = models.CharField(max_length=255, unique=True)
        platform = models.CharField(max_length=20, choices=[('ios', 'iOS'), ('android', 'Android'), ('web', 'Web')])
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)
    ```
  - **Behavioral Impact**: This is an intentional architectural enhancement providing multi-device support.
  - **Pruning**: When the Celery task receives an Expo error `DeviceNotRegistered`, it automatically deletes that `DeviceToken` record from the database.

---

### Django Migration Architecture
- **Django App**: `notifications`
- **Asynchronous Task Engine**: **Celery** + **Redis** broker.
- **Trigger**: Django `post_save` signal on `Message` model.
- **Celery Task Implementation (`tasks.py`)**:
  ```python
  @shared_task
  def send_new_message_notification(message_id):
      from chat.models import Message
      from notifications.models import DeviceToken
      import requests
      
      message = Message.objects.select_related('conversation', 'sender__profile').get(id=message_id)
      recipient = message.conversation.get_other_participant(message.sender)
      
      tokens = list(DeviceToken.objects.filter(user=recipient).values_list('token', flat=True))
      if not tokens:
          return
      
      sender_name = message.sender.profile.full_name or "Someone"
      payload = [
          {
              "to": token,
              "sound": "default",
              "title": f"New message from {sender_name}",
              "body": message.content if len(message.content) <= 50 else message.content[:47] + "...",
              "data": {
                  "type": "chat",
                  "conversationId": str(message.conversation.id),
                  "senderId": str(message.sender.id),
              }
          }
          for token in tokens
      ]
      
      response = requests.post("https://exp.host/--/api/v2/push/send", json=payload)
      # Parse response and remove invalid tokens if DeviceNotRegistered returned
  ```
- **Endpoints**:
  - `POST /api/v1/notifications/devices/` -> Registers or updates current device token (`{ "token": "ExponentPushToken[...]", "platform": "ios" }`).
  - `DELETE /api/v1/notifications/devices/<str:token>/` -> Deregisters token on user sign-out.

---

## 10. Domain: Storage & Media

### Storage Buckets & Configurations

| Bucket Name | Access Visibility | File Size Limit | Allowed MIME Types | Storage Path Convention | Purpose & Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`avatars`** | **Public** | ~5 MB | `image/*` | `${userId}/avatar.${ext}` | Student profile pictures. Uploaded via `src/utils/imageUpload.ts`. Retrievable via `getPublicUrl`. Upsert enabled. |
| **`student-ids`** | **Private** | 5,242,880 bytes (5MB) | `image/jpeg`, `image/png`, `application/pdf` | `${userId}/letter.${ext}` | School admission letters / Student ID cards. Uploaded in `VerificationScreen.tsx`. Read via `createSignedUrl` in `AdminScreen.tsx`. |

### Storage Security Policies (RLS)
Source: `supabase/storage_setup.sql` & `supabase_schema.sql:99-130`

```sql
-- Bucket 'student-ids'
CREATE POLICY "Users can upload their own student IDs" ON storage.objects FOR INSERT TO authenticated
WITH CHECK (bucket_id = 'student-ids' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can view their own student IDs" ON storage.objects FOR SELECT TO authenticated
USING (bucket_id = 'student-ids' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can update their own student IDs" ON storage.objects FOR UPDATE TO authenticated
USING (bucket_id = 'student-ids' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can delete their own student IDs" ON storage.objects FOR DELETE TO authenticated
USING (bucket_id = 'student-ids' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Admins can view all student IDs" ON storage.objects FOR SELECT TO authenticated
USING (bucket_id = 'student-ids' AND EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true));
```

### Storage Touchpoints in Code

| Screen / Util | Bucket | Action | Code Reference |
| :--- | :--- | :--- | :--- |
| `uploadAvatarToSupabase` | `avatars` | `.upload(filePath, arrayBuffer, { upsert: true })` | [`src/utils/imageUpload.ts:20`](file:///home/victor/Desktop/RoomieSync/src/utils/imageUpload.ts#L20) |
| `uploadAvatarToSupabase` | `avatars` | `.getPublicUrl(filePath)` | [`src/utils/imageUpload.ts:29`](file:///home/victor/Desktop/RoomieSync/src/utils/imageUpload.ts#L29) |
| `VerificationScreen.uploadId` | `student-ids` | `.upload(filePath, arrayBuffer, { upsert: true, contentType })` | [`src/screens/VerificationScreen.tsx:60`](file:///home/victor/Desktop/RoomieSync/src/screens/VerificationScreen.tsx#L60) |
| `AdminScreen.VerificationCard`| `student-ids` | `.createSignedUrl(item.school_id_url, 60)` | [`src/screens/AdminScreen.tsx:106`](file:///home/victor/Desktop/RoomieSync/src/screens/AdminScreen.tsx#L106) |

### Identified Storage Bugs in Current Code
1. **60-Second Signed URL Expiration Bug**: In [`src/screens/AdminScreen.tsx:106`](file:///home/victor/Desktop/RoomieSync/src/screens/AdminScreen.tsx#L106), `createSignedUrl(item.school_id_url, 60)` sets an expiry of only 60 seconds. Admins reviewing verification documents encounter broken image links if they spend more than one minute reviewing records. In Django, replace with pre-signed URLs having a 30- to 60-minute lifetime or protected media streaming.
2. **Listing Images Storage Gap**: In `ListingForm.tsx` and `CreateListingScreen.tsx`, local picker URIs (`file:///...`) were passed directly into the `images` payload array rather than being uploaded to a dedicated storage bucket prior to database insertion.

### Django Migration Architecture
- **Storage Backend**: `django-storages` with Amazon S3 or Cloudinary.
- **Buckets / Folders**:
  - `public/avatars/`: Public read access.
  - `private/student_ids/`: Private ACL, accessible only via Django authenticated views or S3 signed URLs (minimum 30-minute expiry).
  - `public/listings/`: Dedicated model `ListingImage` with image uploads.

---

## 11. Domain: Client Caching & Offline State (AsyncStorage)

The application utilizes AsyncStorage to maintain local offline state across app restarts and unauthenticated sessions:

| Storage Key | Data Stored | Screens / Files Involved | Purpose & Description |
| :--- | :--- | :--- | :--- |
| **`@pending_profile`** | JSON String (`ProfileSetupData & PreferencesData & LifestyleData`) | [`LifestyleSurveyScreen.tsx:137`](file:///home/victor/Desktop/RoomieSync/src/screens/LifestyleSurveyScreen.tsx#L137), [`AuthContext.tsx:53, 68`](file:///home/victor/Desktop/RoomieSync/src/context/AuthContext.tsx#L53) | Staged user profile created during initial onboarding before the user signs up. Automatically posted to `profiles` on login/signup and deleted. |
| **`last_read_${conversationId}`** | ISO 8601 Timestamp String | [`ChatScreen.tsx:112`](file:///home/victor/Desktop/RoomieSync/src/screens/ChatScreen.tsx#L112), [`ConversationsScreen.tsx:40-47`](file:///home/victor/Desktop/RoomieSync/src/screens/ConversationsScreen.tsx#L40-L47), [`MessageContext.tsx:21-27`](file:///home/victor/Desktop/RoomieSync/src/context/MessageContext.tsx#L21-L27) | Tracks the exact timestamp when a user last viewed a conversation. Compared against `messages.created_at` to compute unread badges. |
| **`@has_seen_onboarding`** | `'true'` or `'false'` | [`OnboardingScreen.tsx:47`](file:///home/victor/Desktop/RoomieSync/src/screens/OnboardingScreen.tsx#L47), [`AppNavigator.tsx:79`](file:///home/victor/Desktop/RoomieSync/src/navigation/AppNavigator.tsx#L79) | Gates the 3-step carousel splash screen. |
| **`@roomiesync_theme_mode`**| `'light'`, `'dark'`, `'system'` | [`ThemeContext.tsx:30, 53`](file:///home/victor/Desktop/RoomieSync/src/context/ThemeContext.tsx#L30) | Stores user theme preference. |
| **Supabase Session Keys** | JWT Auth Session JSON | [`src/lib/supabase.ts:15, 24, 33`](file:///home/victor/Desktop/RoomieSync/src/lib/supabase.ts#L15) | Stored by Supabase JS SDK storage wrapper. |

---

## Complete Django Architecture Mapping Specification

This matrix defines the target Django architecture corresponding to every component in the current Supabase stack.

| Domain | Supabase Artifact / Pattern | Proposed Django App | Django Models & Fields | DRF Serializers & Views | Realtime / Background Equivalent |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Auth** | `auth.users` + JWT | `accounts` | `User(AbstractBaseUser)`: `id` (UUID PK), `email` (unique), `password`, `is_email_verified` (BooleanField, default=False). | `UserRegisterSerializer`, `VerifyEmailSerializer`, `TokenObtainPairView`, `TokenRefreshView`. | Celery task sending OTP verification email upon registration; JWT blacklisting on logout. |
| **Profiles** | `public.profiles` | `profiles` | `Profile(models.Model)`: OneToOne to `User`. Full lifestyle habits, budget range, academic details, `is_verified`, `is_admin`, `searching_for`. *(Deprecated `has_room_info` dropped)*. | `ProfileSerializer`, `ProfileDetailView`, `ProfileUpdateView`. | Cache invalidation signals on profile update. |
| **Listings** | `public.listings` | `listings` | `Listing`: user (FK, non-null), title, description, price, location, type, searching_for, is_available.<br>`ListingImage`: listing (FK), image (ImageField), order.<br>*(Scaffolding `creator_name_demo` dropped)*. | `ListingSerializer`, `ListingDetailSerializer`, `ListingViewSet` (FilterSet for location/search/budget). | Django signals to clean up image files on S3 upon delete. |
| **Matching** | Client JS `calculateMatchPercentage` | `matching` | None (or Redis match cache). *(Mock 85% fallback dropped)*. | `MatchingService.calculate(p1, p2)`, dynamic calculation in `ListingSerializer.to_representation`. | Celery task for pre-computing batch daily match recommendations. |
| **Chat** | `conversations`, `messages`, Realtime | `chat` | `Conversation`: user1 (FK), user2 (FK), created_at.<br>`Message`: conversation (FK), sender (FK), content, is_read, created_at. | `ConversationSerializer`, `MessageSerializer`, `ConversationViewSet`, `MessageListView`. | **Django Channels** `ChatConsumer` (WebSocket) with Redis channel layer; groups per conversation. Enforce canonical ordering in `save()`. |
| **Moderation**| `reports`, `blocks` | `moderation` | `Report`: reporter, reported_user, listing, reason, status.<br>`Block`: blocker, blocked. Unique together. | `ReportCreateSerializer`, `BlockViewSet` (list/create/destroy). | Custom QuerySet filter mixin excluding blocked users across all feeds. |
| **Verification**| `student-ids` bucket + `is_verified` | `verification` | `VerificationRequest`: user (OneToOne), document (FileField), status, reviewed_at, reviewer (FK). | `VerificationUploadSerializer`, `AdminVerificationViewSet`. | Signal/Celery task sending push notification on approval. |
| **Admin** | `profiles.is_admin` + RLS | `admin_panel` | Same as above. Uses `is_staff` / `is_superuser`. | Custom DRF admin views with `permission_classes=[IsAdminUser]`. | Django Admin dashboard integration (`admin.site.register`). |
| **Notifications**| Edge Functions + Expo API | `notifications` | `DeviceToken`: user (FK), token (CharField, unique), platform (CharField). *(Replaces 1:1 `profiles.push_token` with multi-device support)*. | `DeviceTokenSerializer`, `DeviceTokenViewSet`. | **Celery task** triggering HTTP request to Expo Push API on `Message` creation (porting `send-notification` logic). |
| **Storage** | Supabase Storage Buckets (`avatars`, `student-ids`) | `core.storage` | Media models using `django-storages` (S3 / Cloudinary). | Direct multipart uploads to DRF endpoints or pre-signed S3 upload URLs. | Signed URL generation view for admin with 30m+ expiry (fixing 60s bug). |

---

## Unverified Assumptions Checklist & Migration Decision Log

### Part A: Unverified Database Assumptions (Requires Manual Testing)

> [!WARNING]
> Because the live Supabase project was deleted prior to audit, the following database-level behaviors were reconstructed from client-side code and commit history. They cannot be confirmed against a live database dump and MUST be verified via manual test cases during migration.

- [ ] **RLS Policy Reconstructions**: Reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.
  - *Assumption*: Regular users can only read their own reports and blocks, while admins can read all reports (`supabase_schema.sql:187-196`).
  - *Assumption*: Profiles are publicly readable by any authenticated user (`supabase_schema.sql:52`).
  - *Assumption*: Only users with `is_admin = TRUE` were allowed to update `profiles.is_verified` (`supabase_schema.sql:133-141`).
- [ ] **Database Triggers & Webhooks**: Reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.
  - *Assumption*: The only active PostgreSQL trigger was `on_message_created` invoking `send-notification` (`supabase/enable_notifications.sql`). Confirm whether any triggers existed for auto-creating profile rows on `auth.users` insertion.
- [ ] **Listing Images Storage Type**: Reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.
  - *Assumption*: The database column `listings.images` was either a Postgres `TEXT[]` array or `JSONB` array of image URLs. In `CreateListingScreen.tsx:36`, error code `PGRST204` was handled specifically because this column did not initially exist in production.
- [ ] **Deleted Account Cascades**: Reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.
  - *Assumption*: Deleting a profile from `profiles` cascaded to `listings`, `conversations`, `messages`, `reports`, and `blocks` via `ON DELETE CASCADE`. In Django, ensure `User` model cascades appropriately.
- [ ] **Conversation User Order Unique Constraint**: Reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.
  - *Assumption*: The SQL table has `UNIQUE(user1_id, user2_id)`. However, Supabase does not enforce bi-directional uniqueness `(A, B) == (B, A)` unless an expression index `UNIQUE (LEAST(user1_id, user2_id), GREATEST(user1_id, user2_id))` was defined. In Django, enforce canonical ordering `(min(u1, u2), max(u1, u2))` in `Conversation.save()`.
- [ ] **Storage Bucket MIME & Size Limits**: Reconstructed from client behavior — not confirmed against source, verify via manual testing before migration.
  - *Assumption*: `student-ids` bucket had a hard 5MB limit and restricted types `image/jpeg, image/png, application/pdf` based on `supabase/storage_setup.sql`.

---

### Part B: Resolved Architectural Decisions

| # | Topic | Supabase State | Resolved Django Decision | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Live Notification Function** | Two functions in repo (`notify-message` & `send-notification`). | **Port `send-notification` ONLY.** Discard `notify-message`. | `supabase/enable_notifications.sql` trigger called `send-notification`. Client response listener ([`useNotifications.ts:88`](file:///home/victor/Desktop/RoomieSync/src/hooks/useNotifications.ts#L88)) requires `{ type: 'chat', senderId }`, which only `send-notification` emits. |
| **2** | **`has_room_info` Column** | `JSONB` on `profiles`, only declared in TypeScript interface. | **DROP `has_room_info` from Django Profile model.** | Zero screens or hooks read or write this column. It is obsolete schema debt from pre-listings development (commit `2b4d4d4`). |
| **3** | **Development Scaffolding** | `creator_name_demo` on `listings`; 85% match fallback for null `user_id`. | **DROP `creator_name_demo`. Enforce non-nullable `user` FK.** | Scaffolding was used to display mock seed cards. Production listings require genuine registered creators and calculated matches. |
| **4** | **Email Verification Strategy** | Handled invisibly by Supabase Auth with automated email. | **Implement explicit Token/OTP verification flow via Celery.** | `POST /api/v1/auth/verify-email/` with `is_email_verified` flag on `User`. Prevents unverified account activity while matching user expectations. |
| **5** | **Push Token Model** | 1:1 `profiles.push_token TEXT` (single device per user). | **Create `DeviceToken` table (Many-to-One).** | Deliberate upgrade supporting multi-device notifications. Reinstalls or logins on multiple devices will deliver notifications to all active devices. |
| **6** | **Third-Party SDKs** | Unspecified. | **Confirmed 0 third-party telemetry/analytics SDKs.** | Audit of `.env`, `app.json`, and `package.json` confirmed only Supabase and Expo Push API communicate externally. |
