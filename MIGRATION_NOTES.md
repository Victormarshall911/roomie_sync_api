# RoomieSync Django + DRF Backend — Migration & Architecture Notes

## 1. Executive Summary

This document serves as the comprehensive architectural specification and migration record for the **RoomieSync** backend. The platform has transitioned from a legacy Supabase-based BaaS architecture to an enterprise-grade, custom-engineered **Django 5+ / Django REST Framework (DRF)** backend backed by **PostgreSQL**, **Redis**, **Celery**, and **Django Channels (WebSockets via Daphne)**.

All legacy schema compromises, client-side caching dependencies, unauthenticated demo fallbacks, and security vulnerabilities identified in the audit (`BACKEND_AUDIT.md`) have been resolved.

---

## 2. Global Architecture & Technology Stack

| Layer | Technology | Description |
| :--- | :--- | :--- |
| **Language & Runtime** | Python 3.12+ | Strongly typed, async-capable runtime. |
| **Web Framework** | Django 5+ / DRF | Core REST APIs, ORM, serializers, authentication, and permissions. |
| **Asynchronous & Realtime** | Django Channels 4+ & Daphne | ASGI protocol server for WebSockets (`ws://`) and HTTP (`http://`). |
| **Database** | PostgreSQL 16+ | Relational storage with strict foreign keys and UUID primary keys throughout. |
| **Cache & Task Broker** | Redis 7+ | OTP token storage with TTL, Channels channel layer, and Celery broker. |
| **Background Tasks** | Celery 5+ | Asynchronous email dispatch and Expo push notification delivery. |
| **Authentication** | `djangorestframework-simplejwt` | Stateless JWT access/refresh tokens with blacklist support on logout. |
| **Storage Engine** | `django-storages` + `boto3` | AWS S3 production storage with graceful local `FileSystemStorage` fallback. |

---

## 3. Legacy Supabase Cleanups & Architectural Upgrades

### 3.1. Elimination of `has_room_info`
* **Legacy Problem**: The legacy Supabase `profiles` table maintained an ambiguous, redundant boolean `has_room_info` that went out of sync whenever a user created or deleted a listing.
* **Django Solution**: Dropped `has_room_info` entirely. A user's room status is dynamically derived through relational queries (`user.listings.filter(is_available=True).exists()`) or explicitly through the `searching_for` field (`'Looking for Roommate'` vs `'Listing a Space'`).

### 3.2. Elimination of `creator_name_demo` Scaffolding
* **Legacy Problem**: Legacy listing code permitted unauthenticated/anonymous listing creation that injected arbitrary mock strings into `creator_name_demo` without user relation.
* **Django Solution**: Removed `creator_name_demo`. The `Listing` model enforces a non-nullable `ForeignKey(User, on_delete=CASCADE, related_name='listings')`. Only authenticated, email-verified, and approved student accounts can create listings.

### 3.3. Resolution of the 60-Second Signed URL Bug
* **Legacy Problem**: In `AdminScreen.tsx:106`, `createSignedUrl(item.school_id_url, 60)` set an expiry of only 60 seconds. Admins reviewing verification documents encountered broken image links if reviewing for over a minute.
* **Django Solution**: Implemented a secure Django `TimestampSigner` (local fallback) and AWS S3 presigned URL generator configured with a **1800-second (30-minute)** lifetime (`DOCUMENT_SIGNED_URL_EXPIRY_SECONDS = 1800`), verified by automated regression tests asserting `expires_in != 60`.

### 3.4. Server-Side Read Receipts Replacing Client AsyncStorage
* **Legacy Problem**: Message read receipts in the React Native client were stored in volatile client storage (`AsyncStorage.getItem('last_read_' + id)`), causing unread counts to desynchronize across multiple devices or app re-installs.
* **Django Solution**: `Message` model introduces an indexed server-side `is_read = models.BooleanField(default=False)` field alongside a dedicated REST endpoint `POST /api/v1/chat/conversations/<id>/read/` and real-time badge updates over WebSockets.

### 3.5. Multi-Device Push Notification Architecture
* **Legacy Problem**: Storing a single `expo_push_token` column on `Profile` caused tokens to be overwritten when users logged into multiple devices (e.g., iPhone + iPad), stranding notifications on previous devices.
* **Django Solution**: Introduced a dedicated `DeviceToken` model supporting multiple devices per user (`One-to-Many`), unique per token string, with automatic pruning when Expo returns `DeviceNotRegistered`.

### 3.6. Ephemeral Redis OTP Storage
* **Legacy Problem**: Storing plaintext OTP tokens in database tables risks credential leakage during backups and requires manual deletion cronjobs.
* **Django Solution**: 6-digit OTP codes are stored strictly in Redis cache under key `email_otp:<email>` with a strict 900-second (15-minute) TTL (`cache.set(key, otp, timeout=900)`). Once verified, the key is immediately purged.

### 3.7. Automated Media Cleanup Signals
* **Legacy Problem**: In legacy storage, updating an avatar or deleting a listing left orphaned files in the storage bucket indefinitely.
* **Django Solution**: Implemented Django `pre_save` and `post_delete` signals across `Profile`, `ListingImage`, and `VerificationRequest` that automatically delete replaced or removed assets from S3 or local storage.

---

## 4. Domain Data Models & Schema Specification

All primary keys are UUIDv4.

### 4.1. Domain: Accounts (`accounts`)
* **`User`** (`db_table='users'`):
  - `id`: UUID (PK, default `uuid.uuid4`)
  - `email`: EmailField (unique, indexed)
  - `is_email_verified`: BooleanField (default `False`)
  - `is_active`: BooleanField (default `True`)
  - `is_staff`: BooleanField (default `False`)
  - `created_at`: DateTimeField (auto_now_add)
  - `updated_at`: DateTimeField (auto_now)

### 4.2. Domain: Profiles (`profiles`)
* **`Profile`** (`db_table='profiles'`):
  - `user`: OneToOneField(User, primary_key=True, related_name='profile')
  - `full_name`: CharField (max_length=255)
  - `university`: CharField (max_length=255)
  - `department`: CharField (max_length=255)
  - `gender`: CharField choices (`Male`, `Female`, `Non-binary`, `Prefer not to say`)
  - `budget_min`: PositiveIntegerField (default 0)
  - `budget_max`: PositiveIntegerField (default 300,000)
  - `location_preference`: CharField (max_length=255)
  - `sleep_habit`: CharField choices (`Night Owl`, `Early Bird`)
  - `cleanliness`: PositiveSmallIntegerField (1-10)
  - `socializing`: CharField choices (`Guests often`, `Rarely`)
  - `smoking`: CharField choices (`Yes`, `No`)
  - `noise_level`: CharField choices (`Quiet`, `Moderate`, `Lively`)
  - `study_time`: CharField choices (`Morning`, `Night`, `Varies`)
  - `drinking_habit`: CharField choices (`Often`, `Socially`, `Rarely/Never`)
  - `pets_preference`: CharField choices (`Love them`, `Okay with them`, `Prefer no pets`)
  - `avatar`: ImageField (`upload_to='avatars/%Y/%m/'`, null=True, blank=True)
  - `is_verified`: BooleanField (default `False`)
  - `is_admin`: BooleanField (default `False`)
  - `searching_for`: CharField choices (`Looking for Roommate`, `Listing a Space`, `Already Matched`)

### 4.3. Domain: Listings (`listings`)
* **`Listing`** (`db_table='listings'`):
  - `id`: UUID (PK)
  - `user`: ForeignKey(User, related_name='listings')
  - `title`: CharField (max_length=255)
  - `description`: TextField
  - `price`: PositiveIntegerField (monthly rent)
  - `location`: CharField (max_length=255)
  - `type`: CharField choices (`Room`, `Roommate`)
  - `searching_for`: CharField choices (`Looking for Roommate`, `Listing a Space`)
  - `is_available`: BooleanField (default `True`)
  - `created_at`: DateTimeField (auto_now_add)
  - `updated_at`: DateTimeField (auto_now)
* **`ListingImage`** (`db_table='listing_images'`):
  - `id`: UUID (PK)
  - `listing`: ForeignKey(Listing, related_name='images')
  - `image`: ImageField (`upload_to='listings/%Y/%m/'`)
  - `order`: PositiveIntegerField (default 0)
  - `created_at`: DateTimeField (auto_now_add)

### 4.4. Domain: Moderation (`moderation`)
* **`Report`** (`db_table='reports'`):
  - `id`: UUID (PK)
  - `reporter`: ForeignKey(User, related_name='filed_reports')
  - `reported_user`: ForeignKey(User, related_name='received_reports')
  - `listing`: ForeignKey(Listing, null=True, blank=True)
  - `reason`: TextField
  - `status`: CharField choices (`pending`, `reviewed`, `dismissed`)
  - `created_at`: DateTimeField (auto_now_add)
* **`Block`** (`db_table='blocks'`):
  - `id`: UUID (PK)
  - `blocker`: ForeignKey(User, related_name='blocking')
  - `blocked`: ForeignKey(User, related_name='blocked_by')
  - `created_at`: DateTimeField (auto_now_add)
  - *Unique constraint on `(blocker, blocked)`*

### 4.5. Domain: Chat & Realtime (`chat`)
* **`Conversation`** (`db_table='conversations'`):
  - `id`: UUID (PK)
  - `user1`: ForeignKey(User, related_name='conversations_as_user1')
  - `user2`: ForeignKey(User, related_name='conversations_as_user2')
  - `created_at`: DateTimeField (auto_now_add)
  - `updated_at`: DateTimeField (auto_now)
  - *Enforces canonical sorting on `save()`: `user1 = min(u1, u2)` to prevent duplicate pairwise threads.*
* **`Message`** (`db_table='messages'`):
  - `id`: UUID (PK)
  - `conversation`: ForeignKey(Conversation, related_name='messages')
  - `sender`: ForeignKey(User, related_name='sent_messages')
  - `content`: TextField
  - `is_read`: BooleanField (default `False`, indexed)
  - `created_at`: DateTimeField (auto_now_add, indexed)

### 4.6. Domain: Student Verification (`verification`)
* **`VerificationRequest`** (`db_table='verification_requests'`):
  - `id`: UUID (PK)
  - `user`: OneToOneField(User, related_name='verification_request')
  - `document`: FileField (`upload_to='verification_documents/%Y/'`)
  - `status`: CharField choices (`pending`, `approved`, `rejected`)
  - `rejection_reason`: TextField (blank=True)
  - `reviewed_by`: ForeignKey(User, null=True, blank=True)
  - `submitted_at`: DateTimeField (auto_now_add)
  - `reviewed_at`: DateTimeField (null=True, blank=True)

### 4.7. Domain: Notifications (`notifications`)
* **`DeviceToken`** (`db_table='device_tokens'`):
  - `id`: UUID (PK)
  - `user`: ForeignKey(User, related_name='device_tokens')
  - `token`: CharField (max_length=255, unique=True, indexed)
  - `platform`: CharField (max_length=20, default='expo')
  - `created_at`: DateTimeField (auto_now_add)

---

## 5. API Endpoint Directory

### Authentication (`/api/v1/auth/`)
* `POST /api/v1/auth/register/` — Register student; accepts nested onboarding profile payload (`profile: {...}`). Returns JWT tokens and dispatches OTP.
* `POST /api/v1/auth/verify-email/` — Verifies 6-digit OTP from Redis (`email`, `code`). Toggles `is_email_verified=True`.
* `POST /api/v1/auth/resend-code/` — Generates and resends fresh OTP.
* `POST /api/v1/auth/token/` — Login with email/password; returns JWT access/refresh tokens and user metadata.
* `POST /api/v1/auth/token/refresh/` — Refresh access token.
* `POST /api/v1/auth/logout/` — Blacklists refresh token.
* `DELETE /api/v1/auth/me/` — Self-serve GDPR account deletion.

### Profiles (`/api/v1/profiles/`)
* `GET /api/v1/profiles/me/` — Fetch authenticated student's full profile.
* `PATCH /api/v1/profiles/me/` — Partial update lifestyle, budget, location, or avatar (`multipart/form-data`). Read-only guards on `is_verified` and `is_admin`.
* `GET /api/v1/profiles/<uuid:pk>/` — Fetch public profile; strips private fields (`email`, `is_admin`). Computes `match_percentage`.

### Listings (`/api/v1/listings/`)
* `GET /api/v1/listings/` — Filterable listings feed (`location`, `min_price`, `max_price`, `type`, `searching_for`). Automatically filters out listings created by blocked users.
* `POST /api/v1/listings/` — Create listing with multiple image uploads (`uploaded_images: [File, File, ...]`).
* `GET /api/v1/listings/<uuid:pk>/` — Fetch listing detail with ordered images and creator public profile.
* `PATCH /api/v1/listings/<uuid:pk>/` — Owner-only update.
* `DELETE /api/v1/listings/<uuid:pk>/` — Owner-only delete.
* `POST /api/v1/listings/<uuid:pk>/toggle-availability/` — Owner-only toggle `is_available`.

### Matching (`/api/v1/matches/`)
* `GET /api/v1/matches/` — Computes pairwise compatibility scores against all active profiles in the system, ordered descending by score. Excludes blocked users and self.

### Moderation (`/api/v1/moderation/`)
* `POST /api/v1/moderation/reports/` — Report an abusive user or fraudulent listing (`reported_user_id`, `listing_id`, `reason`).
* `POST /api/v1/moderation/blocks/` — Block an abusive user (`blocked_id`). Triggers immediate exclusion across listings, matching, and conversations.
* `DELETE /api/v1/moderation/blocks/<uuid:blocked_id>/` — Unblock user.
* `GET /api/v1/moderation/blocks/` — List all blocked users.

### Chat & Messaging (`/api/v1/chat/`)
* `GET /api/v1/chat/conversations/` — List conversation inbox with latest message snippet, unread message count, and other participant profile.
* `POST /api/v1/chat/conversations/` — Start or retrieve canonical conversation with participant (`recipient_id`).
* `GET /api/v1/chat/conversations/<uuid:id>/messages/` — Paginated message history (cursor/limit) for thread.
* `POST /api/v1/chat/conversations/<uuid:id>/messages/` — REST fallback message send.
* `POST /api/v1/chat/conversations/<uuid:id>/read/` — Mark all unread messages from other participant as read.

### Real-time WebSockets (`/ws/chat/<uuid:conversation_id>/`)
* **Protocol**: WebSocket (ASGI / Django Channels).
* **Authentication**: `JWTAuthMiddleware` via `?token=<access_token>` or `Authorization: Bearer <access_token>`.
* **Events**:
  - `send_json`: `{"content": "Hello!"}` (also accepts `{"message": "Hello!"}`).
  - `chat_message` broadcast: `{"type": "new_message", "message": {...}}`.
  - Personal group badge broadcast: `{"type": "unread_badge_update", "data": {"type": "new_message", "conversation_id": "...", "message_id": "..."}}`.

### Student Verification (`/api/v1/verification/`)
* `POST /api/v1/verification/submit/` — Upload student ID or admission letter (`document`, max 5MB, PDF/JPEG/PNG). Prevents duplicate pending requests.
* `GET /api/v1/verification/status/` — Check current student verification status (`pending`, `approved`, `rejected`, `rejection_reason`).

### Admin Management (`/api/v1/admin/`)
* `GET /api/v1/admin/verifications/` — List pending student verification requests. Restricted to `is_admin=True` profile users.
* `GET /api/v1/admin/verifications/<uuid:user_id>/document/` — Generates a signed document preview URL valid for 30 minutes (`1800s`). When accessed with `?token=...`, securely streams document.
* `POST /api/v1/admin/verifications/<uuid:user_id>/approve/` — Approves verification request, sets `profile.is_verified=True`, and dispatches push/email notification.
* `POST /api/v1/admin/verifications/<uuid:user_id>/reject/` — Rejects request with reason (`reason: "..."`), sets `is_verified=False`, and notifies student.

### Push Notifications (`/api/v1/notifications/`)
* `POST /api/v1/notifications/devices/` — Register Expo device push token (`token: "ExponentPushToken[...]"`, `platform: "ios"|"android"`). Supports multi-device registration.
* `DELETE /api/v1/notifications/devices/` — Unregister token on logout.

---

## 6. Roommate Matching Algorithm Specification

Source: [`RoomieSync/src/utils/matching.ts:31-142`](file:///home/victor/Desktop/RoomieSync/src/utils/matching.ts#L31-L142) and [`BACKEND_AUDIT.md:290-304`](file:///home/victor/Desktop/roomie_sync_api/BACKEND_AUDIT.md#L290-L304).

The compatibility calculation in `matching/services.py:calculate_match(p1, p2)` faithfully ports the original TypeScript implementation across all 9 traits:

| Trait | Weight | Calculation Logic & Evaluation Criteria |
| :--- | :--- | :--- |
| **Budget Overlap** | **25% (0.25)** | Overlap ratio between `[p1.min, p1.max]` and `[p2.min, p2.max]`. If `maxMin <= minMax`, ratio is `(overlapRange * 2) / (p1Range + p2Range)`. Score added = `min(ratio, 1.0) * 0.25`. |
| **Location Preference** | **15% (0.15)** | Case-insensitive trimmed exact string match = 100% (`0.15`). Substring containment (`loc1 in loc2 or loc2 in loc1`) = 70% partial match (`0.15 * 0.7 = 0.105`). Mismatch = 0%. |
| **Cleanliness** | **12% (0.12)** | Difference $\Delta = \|cleanliness_1 - cleanliness_2\|$. If $\Delta = 0$, exact match = 100% (`0.12`). If $\Delta \le 3$, scaled tolerance = $1 - (\Delta / 6)$ multiplied by 0.12. If $\Delta > 3$, score = 0%. |
| **Sleep Habit** | **10% (0.10)** | Exact match (`'Early Bird'` vs `'Early Bird'` or `'Night Owl'` vs `'Night Owl'`) = 100% (`0.10`). Mismatch = 0%. |
| **Noise Level** | **10% (0.10)** | Exact match (`'Quiet'`, `'Moderate'`, `'Lively'`) = 100% (`0.10`). Mismatch = 0%. |
| **Socializing** | **8% (0.08)** | Exact match (`'Guests often'` vs `'Guests often'` or `'Rarely'` vs `'Rarely'`) = 100% (`0.08`). Mismatch = 0%. |
| **Study Time** | **8% (0.08)** | Exact match (`'Morning'`, `'Night'`, `'Varies'`) = 100% (`0.08`). Mismatch = 0%. |
| **Smoking** | **6% (0.06)** | Exact match (`'Yes'` vs `'Yes'` or `'No'` vs `'No'`) = 100% (`0.06`). Mismatch = 0%. |
| **Drinking Habit** | **6% (0.06)** | Exact match (`'Often'`, `'Socially'`, `'Rarely/Never'`) = 100% (`0.06`). Mismatch = 0%. |

### Normalization & Fallback
- **Missing Trait Handling**: When a student has omitted optional lifestyle answers, the denominator scales dynamically to only evaluate answered traits common to both profiles ($\sum W_{answered}$). Students are not penalized for unanswered optional questions.
- **Baseline Fallback**: If zero common traits are answered by both students (`total_weight == 0`), the algorithm returns a safe baseline score of **50%**.
- **Rounding**: Final score is rounded to the nearest integer: `round((score / total_weight) * 100)`.

---

## 7. Storage & Media Management

1. **Public vs Private Segregation**:
   - `avatars/`: Publicly readable (`/media/avatars/...` or S3 public read).
   - `listings/`: Publicly readable (`/media/listings/...` or S3 public read).
   - `verification_documents/`: **Strictly private**. In local dev, direct media access is blocked in favor of the admin signed stream endpoint `/api/v1/admin/verifications/<user_id>/document/?token=...`. In S3 production, time-limited presigned S3 URLs (30-minute validity) are generated on demand.
2. **Local Development Fallback**:
   - When AWS S3 credentials are missing from `.env`, `roomiesync/settings.py` prints a prominent warning banner to stderr and automatically falls back to Django's `FileSystemStorage` under `./media/`.

---

## 8. Verification & Test Suite Summary

The entire test suite consists of **64 automated tests** across all 10 domain areas and an end-to-end user lifecycle test, achieving a 100% pass rate.

```
============================= test session starts ==============================
accounts/tests/test_auth.py .........                                    [ 14%]
admin_management/tests/test_admin.py .....                               [ 21%]
chat/tests/test_chat_rest.py ......                                      [ 31%]
listings/tests/test_listings.py ........                                 [ 43%]
matching/tests/test_matching.py .                                        [ 45%]
moderation/tests/test_moderation.py ....                                 [ 51%]
notifications/tests/test_notifications.py .....                          [ 59%]
profiles/tests/test_profiles.py .....                                    [ 67%]
roomiesync/tests/test_storage.py .....                                   [ 75%]
verification/tests/test_verification.py .....                            [ 82%]
chat/tests/test_chat_ws.py ...                                           [ 87%]
roomiesync/tests/test_e2e_journey.py .                                   [ 89%]
matching/tests/test_matching.py .......                                  [100%]

======================== 64 passed in 130.70s (0:02:10) ========================
```

---

## 9. Local Development & Deployment Runbook

### Prerequisites
- Python 3.12+
- Docker & Docker Compose (for PostgreSQL and Redis)

### Running Database & Redis
```bash
docker run -d --name roomiesync_postgres -e POSTGRES_DB=roomiesync -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5433:5432 postgres:16-alpine
docker run -d --name roomiesync_redis -p 6379:6379 redis:7-alpine
```

### Environment Setup
```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

### Running the Services
1. **ASGI Web & WebSocket Server**:
   ```bash
   daphne -b 0.0.0.0 -p 8000 roomiesync.asgi:application
   ```
2. **Celery Task Worker**:
   ```bash
   celery -A roomiesync worker --loglevel=info
   ```
3. **Execute Test Suite**:
   ```bash
   pytest
   ```
