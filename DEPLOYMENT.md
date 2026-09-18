# RoomieSync Production Deployment & Operations Runbook

This document details the production cloud infrastructure, environment configuration, provisioning steps, and verification procedures for deploying the **RoomieSync** backend (Django 5+, Django REST Framework, Daphne ASGI, Channels, Celery) to cloud hosting.

---

## 1. Production Topology & Architecture

```
                                  +---------------------------+
                                  |   React Native / Expo     |
                                  |      Mobile Client        |
                                  +-------------+-------------+
                                                |
                               +----------------+---------------+
                               |                                |
                        HTTPS (REST API)                 WSS (WebSockets)
                               |                                |
                               v                                v
                   +---------------------------------------------------------+
                   |                 Render Web Service                      |
                   |               `roomiesync-api` (ASGI)                   |
                   |       Daphne: `0.0.0.0:$PORT roomiesync.asgi`           |
                   |      Static Assets: WhiteNoise Compressed Storage       |
                   +-------+--------------------+-------------------+-------+
                           |                    |                   |
                           v                    v                   v
                +--------------------+  +---------------+  +--------------------+
                |   Neon PostgreSQL  |  |  Hosted Redis |  |   Cloudflare R2    |
                |  (Branching DB)    |  | (Upstash/     |  |   (S3-Compatible)  |
                |  SSL: require      |  |  Render)      |  |                    |
                |  Pooled/Direct     |  |               |  | avatars/ (Public)  |
                +--------------------+  +-------+-------+  | listings/ (Public) |
                                                |          | verif/ (Private)   |
                                                |          +--------------------+
                                                v
                                  +---------------------------+
                                  |  Render Background Worker |
                                  |    `roomiesync-worker`    |
                                  |   Celery: Push / Emails   |
                                  +---------------------------+
```

---

## 2. Infrastructure Services

| Service | Provider | Purpose | Free Tier / Cost Notes |
| :--- | :--- | :--- | :--- |
| **Compute (Web)** | [Render](https://render.com) | Daphne ASGI server (`http://` + `ws://`) | Free tier available. Spins down after 15m of inactivity (cold start 50–90s). |
| **Compute (Worker)** | [Render](https://render.com) | Celery task runner (Push notifications, OTP) | Requires **Starter tier ($7/mo)**; Render has no free worker tier. *Workaround: `CELERY_TASK_ALWAYS_EAGER=True` executes tasks in-process for free testing.* |
| **Database** | [Neon](https://neon.tech) | PostgreSQL 16+ with connection pooling | Free tier includes 0.5 GB storage, auto-suspend, instant branching. |
| **Cache & Broker** | [Upstash](https://upstash.com) or [Render Redis](https://render.com) | OTP token cache, Channels layer, Celery broker | Upstash offers free tier (10k commands/day, TLS `rediss://`). Render Redis is $7/mo. |
| **Media Storage** | [Cloudflare R2](https://cloudflare.com) | Avatars, listing photos, verification IDs | **Zero egress fees**. 10 GB free storage/month. S3-compatible API. |

---

## 3. Environment Variables Specification

Set the following variables in the Render Dashboard (or via `render.yaml`):

```env
# Core Django
DEBUG=False
SECRET_KEY=generate-a-strong-random-50-char-string-for-production
ALLOWED_HOSTS=.onrender.com,localhost,127.0.0.1
RENDER_EXTERNAL_HOSTNAME=roomiesync-api.onrender.com

# Database (Neon)
# Neon connection strings must include ?sslmode=require
DATABASE_URL=postgresql://user:password@ep-cool-snowflake-123456.us-east-2.aws.neon.tech/neondb?sslmode=require

# Hosted Redis
# Single instance serving Cache (rs_cache:), Channels (rs_channels:), and Celery
REDIS_URL=rediss://default:password@us1-quick-falcon-12345.upstash.io:6379
CELERY_BROKER_URL=rediss://default:password@us1-quick-falcon-12345.upstash.io:6379
# Set to 'False' when using a separate Render Background Worker; 'True' for in-process eager execution:
CELERY_TASK_ALWAYS_EAGER=False

# Media Storage (Cloudflare R2)
AWS_ACCESS_KEY_ID=your_r2_access_key_id
AWS_SECRET_ACCESS_KEY=your_r2_secret_access_key
AWS_STORAGE_BUCKET_NAME=roomiesync-media
AWS_S3_ENDPOINT_URL=https://<your_cloudflare_account_id>.r2.cloudflarestorage.com
# Use the R2 public development URL or your custom domain:
AWS_S3_CUSTOM_DOMAIN=pub-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.r2.dev
AWS_S3_REGION_NAME=auto

# Security
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
CSRF_TRUSTED_ORIGINS=https://roomiesync-api.onrender.com
```

---

## 4. Cloudflare R2 Media Bucket Configuration

To ensure public/private separation works correctly with Cloudflare R2:

1. **Create Bucket**: Name e.g. `roomiesync-media`.
2. **Enable Public Access**:
   - In Cloudflare Dashboard -> **R2** -> `roomiesync-media` -> **Settings** -> **Public Access**:
     - Either enable **R2.dev subdomain** (e.g. `https://pub-xxxx.r2.dev`)
     - OR connect a custom domain (e.g. `media.roomiesync.app`).
   - Set `AWS_S3_CUSTOM_DOMAIN` to this domain (e.g. `pub-xxxx.r2.dev`).
3. **Public vs Private Segregation**:
   - `avatars/` and `listings/`: Read through `PublicMediaStorage` with `querystring_auth=False`, delivering direct URLs:
     `https://pub-xxxx.r2.dev/avatars/2026/09/avatar.jpg`
   - `verification_documents/`: Read through `PrivateMediaStorage` or `generate_signed_document_url` which uses Boto3 to generate time-limited presigned URLs (1800s / 30-minute expiry) signed with your R2 API credentials. Direct unauthenticated requests to `verification_documents/` will be forbidden if using S3 API directly or path-based restrictions.

---

## 5. Render Deployment Steps

### Option A: Using `render.yaml` Blueprint (Recommended)
1. Commit all files and push to `origin/main` on GitHub:
   ```bash
   git add .
   git commit -m "feat: add production deployment configuration"
   git push origin main
   ```
2. Navigate to [dashboard.render.com](https://dashboard.render.com) -> **Blueprints** -> **New Blueprint Instance**.
3. Select your repository `Victormarshall911/roomie_sync_api`.
4. Render will read `render.yaml` and create:
   - `roomiesync-api` (Web Service)
   - `roomiesync-worker` (Background Worker)
5. Fill in the required environment variables (`DATABASE_URL`, `REDIS_URL`, `AWS_*`) in the Render prompt.
6. Click **Apply**.

### Option B: Manual Web Service Setup
1. In Render Dashboard -> **New** -> **Web Service**.
2. Connect `Victormarshall911/roomie_sync_api`.
3. Configure:
   - **Name**: `roomiesync-api`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Start Command**: `daphne -b 0.0.0.0 -p $PORT roomiesync.asgi:application`
4. Add all environment variables from Section 3 above.

---

## 6. Pre-Flight Database Migration (Dry Run from Local Machine)

Before pointing Render live traffic to Neon, run migrations from your local development environment against Neon:

```bash
DATABASE_URL="postgresql://<user>:<password>@<neon-host>/neondb?sslmode=require" python manage.py migrate
```

Verify tables were created in Neon:
```bash
psql "postgresql://<user>:<password>@<neon-host>/neondb?sslmode=require" -c "\dt"
```
Expected tables:
- `users`, `profiles`
- `listings`, `listing_images`
- `conversations`, `messages`
- `reports`, `blocks`
- `verification_requests`
- `device_tokens`

---

## 7. Operational Nuances & Cost Breakdown

### Render Free Web Tier:
- **Spin Down**: Free web services go to sleep after 15 minutes without incoming traffic.
- **Cold Starts**: The first request after a sleep period takes 50 to 90 seconds to respond.
- **WebSockets**: When an instance spins down or restarts, all active WebSocket connections (`wss://`) will disconnect. The React Native mobile client includes automatic WebSocket reconnection logic to handle this.

### Celery Background Worker Options:
- **Paid Option ($7/mo)**: Run the separate `roomiesync-worker` on Render's Starter plan. This ensures OTP emails and push notifications process off the main thread.
- **Free/Zero-Cost Option**: If you do not wish to pay $7/mo during development, set `CELERY_TASK_ALWAYS_EAGER=True` in the Web Service environment variables. All tasks will execute synchronously in the request-response cycle.

### Cloudflare R2 Costs:
- 10 GB/month free storage.
- $0 egress fees (bandwidth is 100% free).
- Millions of free Class A/B API operations per month.
