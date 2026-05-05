# 🗳️ MatSetu (मतसेतु) — India's AI-powered Digital Election Management Platform

> **EVM Replacement | All-India Edition**  
> 950M voters · 1.4M booths · 800 districts · 36 states/UTs

**MatSetu** is a high-integrity, AI-driven digital voting platform designed to modernize India's electoral process. By integrating biometric face-matching, zero-knowledge proofs, and real-time immutable ledgers, it provides a secure and transparent alternative to traditional EVMs, capable of handling election data at a national scale.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Security Model](#security-model)
- [Quick Start](#quick-start)
- [Environment Configuration](#environment-configuration)
- [Admin Hierarchy](#admin-hierarchy)
- [Voter Auth Flow (12 Steps)](#voter-auth-flow)
- [Uncontested Elections](#uncontested-elections)
- [API Reference](#api-reference)
- [Scripts](#scripts)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Overview

MatSetu replaces India's offline EVMs with a real-time, biometric-authenticated,
cryptographically-secured, end-to-end verifiable digital voting pipeline.

**Core properties:**
- Biometric (ArcFace 512-D) + OTP dual authentication
- SHA-256 hash chain ledger (append-only, immutable)
- ZK anonymous receipts (Helios-style)
- 8-level geographic Redis tally hierarchy
- 7-tier admin scope isolation with TOTP 2FA
- Row Level Security (RLS) on PostgreSQL

---

## Project Structure

```text
.
├── backend/                # FastAPI application source
│   ├── core/               # Security, hashing, and core logic
│   ├── models/             # SQLAlchemy database models
│   ├── routers/            # API endpoints (v1)
│   ├── schemas/            # Pydantic validation schemas
│   ├── services/           # Business logic (Face matching, etc.)
│   └── tasks/              # Celery background tasks
├── frontend/               # Vanilla JS + HTML interfaces
│   ├── admin/              # District/State Admin dashboard
│   ├── booth/              # Polling booth terminal
│   ├── master/             # T1 Master Admin panel
│   └── receipt/            # ZK Receipt verification
├── infra/                  # Infrastructure as Code
│   ├── nginx/              # Reverse proxy configuration
│   └── rls_policies.sql    # PostgreSQL RLS definitions
├── alembic/                # Database migration scripts
├── docker-compose.yml      # Orchestration for all services
└── scripts/                # Enrollment and auditing utilities
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI + Uvicorn + Celery |
| Database | PostgreSQL 16 (RLS) + Redis 7 + Qdrant + TimescaleDB |
| AI/ML | InsightFace Buffalo_L (ArcFace 512-D) + MiniFASNet liveness + Tesseract 5 OCR |
| Auth | bcrypt + TOTP (pyotp) + JWT HS256 + mTLS per booth |
| SMS/OTP | Twilio (primary) / MSG91 (fallback) / Thermal print (R8 fallback) |
| ZK Proofs | Helios-style ZK commitments |
| Frontend | Vanilla HTML + CSS + JavaScript |
| Maps | Leaflet.js + D3.js choropleth |
| Monitoring | Prometheus + Grafana + OpenTelemetry |
| Infra | Docker Compose + NGINX + MinIO |

---

## Architecture

### System Flow Diagram

```text
                    ┌─────────────────────────────────────────────┐
                    │                Election Commission          │
                    └─────────────────────────────────────────────┘
                                            │
                                            ▼
                            ┌─────────────────────────────┐
                            │        Chief Electoral      │
                            │         Officer (CEO)       │
                            └─────────────────────────────┘
                                            │
                                            ▼
                                ┌─────────────────────┐
                                │      State Admin    │
                                └─────────┬───────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
            ┌─────────────────────┐                 ┌─────────────────────┐
            │   District Admin    │                 │   Constituency      │
            │   (36 Districts)    │                 │   Officer (RO)      │
            └─────────┬───────────┘                 └─────────┬───────────┘
                      │                                       │
                      ▼                                       ▼
            ┌─────────────────────┐                     ┌─────────────────────┐
            │       Booth         │                     │    Polling Booth    │
            │ Supervisor (140k)   │                     │   Hardware (R8)     │
            └─────────┬───────────┘                     └─────────┬───────────┘
                      │                                           │
                      ▼                                           ▼
                  ┌─────────┐                               ┌─────────┐
                  │  Voter  │                               │  Face   │
                  │ (1.4M)  │                               │  Match  │
                  └─────────┘                               └─────────┘


                                  ┌────────────────────────┐
                                  │      Voter / User      │
                                  └───────────┬────────────┘
                                              │
                      ┌───────────────────────┼───────────────────────┐
                      ▼                       ▼                       ▼
              ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
              │ Booth Terminal│       │ Admin Dash    │       │ Public Verify │
              │   (Frontend)  │       │   (Frontend)  │       │   (Frontend)  │
              └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
                      │                       │                       │
                      │               ┌───────▼───────┐               │
                      └──────────────►│    NGINX      │◄──────────────┘
                                      │ (Reverse Proxy)│
                                      └───────┬───────┘
                                              │
                                      ┌───────▼───────┐
                                      │  FastAPI App  │       ┌───────────────┐
                                      │   (Backend)   ├──────►│   Qdrant      │
                                      └──────┬─┬──────┘       │ (Vector DB)   │
                                             │ │              └───────────────┘
                      ┌──────────────────────┘ └────────────────────┐
                      ▼                                             ▼
              ┌───────────────┐                             ┌───────────────┐
              │  PostgreSQL   │                             │     Redis     │
              │ (Relational DB)│                             │ (Tally Cache) │
              └───────────────┘                             └───────┬───────┘
                                                                    │
                                                            ┌───────▼───────┐
                                                            │    Celery     │
                                                            │ (Async Tasks) │
                                                            └───────┬───────┘
                                                                    │
                                                            ┌───────▼───────┐
                                                            │   S3 (MinIO)  │
                                                            │ (Face Blobs)  │
                                                            └───────────────┘
```

### Geographic Hierarchy

```
Country → State → Division → District → Taluka → Block → Village → Booth
(8-level geographic hierarchy — Redis tally keys follow this)
```

**Admin Tiers:**
```
T1 MASTER ADMIN   → all_india    → bcrypt + TOTP + IP allowlist (mandatory)
T2 STATE ADMIN    → one_state    → bcrypt + TOTP + IP allowlist (mandatory)
T3 DIVISION ADMIN → one_div      → bcrypt + TOTP
T4 DISTRICT ADMIN → one_dist     → bcrypt + TOTP
T5 CONSTIT. ADMIN → one_const    → bcrypt + TOTP
T6 WORKER         → one_booth    → ArcFace + GPS + mTLS cert
T7 VOTER          → own_const    → ArcFace liveness + mobile OTP
```

---

## Security Model

| Rule | Description |
|------|-------------|
| **SEC-1** | `vote_ledger` is APPEND-ONLY. `UPDATE`/`DELETE` REVOKED at DB role level. |
| **SEC-2** | `has_voted` once TRUE is **IMMUTABLE**. DB trigger enforced. |
| **SEC-3** | All vote operations atomic: Redis pipeline + PostgreSQL transaction. |
| **SEC-4** | RLS always ON. Every query respects `scope_id` from JWT claims. |
| **SEC-5** | OTPs: 5-min expiry, max 3 attempts, stored as SHA-256(otp) only. |
| **SEC-6** | ZK receipts never reveal candidate — only inclusion proof. |
| **SEC-7** | JWT tokens are role-scoped. Cross-scope = immediate REJECT. |
| **SEC-8** | All manual overrides → `ANOMALY_OVERRIDE` in audit_log. |
| **SEC-9** | Election start/stop + UNCONTESTED require TOTP re-confirmation. |
| **SEC-10** | Master Admin has read-only on vote_ledger. No writes ever. |

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11 (for scripts)

### 1. Clone and configure

```bash
git clone https://github.com/eci/matsetu.git
cd matsetu
cp .env.example .env
# Edit .env — set SECRET_KEY, BOOTH_SECRET, DB passwords, Twilio keys
```

### 2. Start all services

```bash
docker-compose up -d
```

Services started:
- PostgreSQL 16: `localhost:5432`
- Redis 7: `localhost:6379`
- Qdrant: `localhost:6333`
- MinIO: `localhost:9000` (console: `localhost:9001`)
- FastAPI: `localhost:8000`
- Celery Worker
- NGINX: `localhost:80`
- Grafana: `localhost:3000`
- Prometheus: `localhost:9090`

### 3. Initialize database & RLS

```bash
# Wait for postgres to be healthy, then:
docker exec matsetu_api python -c "
import asyncio
from backend.database import init_db
asyncio.run(init_db())
"

# Apply RLS policies (after tables created)
docker exec -i matsetu_postgres psql -U matsetu -d matsetu < infra/rls_policies.sql
```

### 4. Create T1 Master Admin

```bash
docker exec matsetu_api python -c "
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import AsyncSessionLocal
from backend.models import AdminAccount
from backend.core import hash_password, generate_totp_secret, encrypt_totp_secret, get_totp_uri
from uuid import uuid4

async def create_master():
    secret = generate_totp_secret()
    admin = AdminAccount(
        id=uuid4(),
        username='master_admin',
        password_hash=hash_password('YourSecurePassword123!'),
        totp_secret=encrypt_totp_secret(secret),
        role='T1',
        scope_type='all_india',
        is_active=True
    )
    async with AsyncSessionLocal() as db:
        db.add(admin)
        await db.commit()
    print('Master admin created!')
    print('TOTP URI:', get_totp_uri(secret, 'master_admin'))

asyncio.run(create_master())
"
```

Scan the TOTP URI with Google Authenticator or Authy.

### 5. Access Frontends

| Interface | URL |
|-----------|-----|
| Booth Terminal | http://localhost/booth/ |
| Admin Dashboard | http://localhost/admin/ |
| Master Admin | http://localhost/master/ |
| Receipt Verification | http://localhost/verify |
| API Docs | http://localhost:8000/api/docs |
| Grafana | http://localhost:3000 |

---

## Environment Configuration

The following variables are required in your `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Secret for JWT signing | `Required` |
| `DATABASE_URL` | PostgreSQL connection string | `Required` |
| `REDIS_URL` | Redis connection string | `Required` |
| `QDRANT_URL` | Qdrant vector DB URL | `Required` |
| `MINIO_URL` | S3 storage URL (MinIO) | `Required` |
| `TWILIO_SID` | Twilio Account SID | `Optional` |
| `TWILIO_TOKEN` | Twilio Auth Token | `Optional` |
| `BOOTH_SECRET` | Secret for booth mTLS/Auth | `Required` |

---

## Voter Auth Flow

11-step EVM replacement:

1. **EPIC Scan** — Tesseract OCR extracts voter_id from card/QR
2. **DB Lookup** — PostgreSQL voters table query
3. **Liveness Check** — MiniFASNet anti-spoofing (FLAG_LIVENESS_FAIL if spoof)
4. **Face Match** — ArcFace 512-D → Qdrant cosine search (FAR < 0.01%)
5. **Fail-safe** — Aadhaar OTP / Thermal print if face fails
6. **has_voted check** — Immediate REJECT if TRUE (SEC-2)
7. **OTP Dispatch** — Celery → Twilio → MSG91 → thermal fallback (R8)
8. **OTP Verify** — Max 3 attempts, 5-min expiry (SEC-5)
9. **Ballot Display** — 22 languages, candidate + party + symbol
10. **Atomic Submit** — DB INSERT + Redis INCR x8 + has_voted=TRUE
11. **ZK Receipt** — Thermal printed, never reveals candidate (SEC-6)

---

## Uncontested Elections

Business rules R1-R8:

| Rule | Description |
|------|-------------|
| R1 | Auto-flag when approved_candidates = 1 after deadline |
| R2 | T1 Master + T2 State 2-admin sign-off + TOTP required |
| R3 | No booths activate, no vote_ledger rows created |
| R4 | Dashboard shows UNCONTESTED badge (no vote count) |
| R5 | Result export: `is_uncontested=TRUE` in JSON |
| R6 | Reject declaration if nomination deadline not passed |
| R7 | Reversible before polls open (same 2-admin sign-off) |
| R8 | OTP_PRINT_FALLBACK: 60-second thermal slip if SMS fails |

API Endpoints:
```
POST   /api/v1/election/uncontested/{constituency_id}  — declare
DELETE /api/v1/election/uncontested/{constituency_id}  — reverse
GET    /api/v1/election/uncontested                    — list all
GET    /api/v1/results/uncontested                     — results view
```

---

## API Reference

Full OpenAPI docs available at: `/api/docs`

### Auth
```
POST /api/v1/auth/admin/login    — Admin login (bcrypt + TOTP)
POST /api/v1/auth/admin/create   — Create admin (T1 only)
POST /api/v1/auth/admin/refresh  — Refresh JWT
```

### Voter Flow
```
POST /api/v1/voter/scan           — EPIC lookup
POST /api/v1/voter/scan-ocr       — OCR card scan
POST /api/v1/voter/face-verify    — ArcFace liveness + match
POST /api/v1/voter/otp/send       — Dispatch OTP
POST /api/v1/voter/otp/verify     — Verify OTP + get ballot token
```

### Voting
```
POST /api/v1/vote/ballot          — Get ballot (candidates)
POST /api/v1/vote/cast            — Submit vote (atomic)
GET  /api/v1/vote/tally/{level}/{id} — Live tally from Redis
GET  /api/v1/vote/verify-receipt/{token} — Public ZK receipt check
```

### Admin
```
GET  /api/v1/admin/dashboard      — Stats
POST /api/v1/admin/booth          — Create booth
POST /api/v1/admin/booth/{id}/activate — Activate (rejects if UNCONTESTED)
POST /api/v1/admin/election/start — Start (TOTP)
POST /api/v1/admin/election/stop  — Stop (TOTP)
GET  /api/v1/admin/anomalies      — List anomaly events
POST /api/v1/admin/anomaly/{id}/override — Override (SEC-8)
GET  /api/v1/admin/audit-log      — Audit trail (SEC-10)
```

### Worker
```
POST /api/v1/worker/login         — Face + GPS + mTLS auth
POST /api/v1/worker/reauth/{id}   — Re-authentication (30min/20votes)
```

### SSE
```
GET /api/v1/sse/tally/national    — National tally stream (5s)
GET /api/v1/sse/tally/booth/{id}  — Booth tally stream (3s)
GET /api/v1/sse/anomalies         — Anomaly event stream (10s)
```

---

## Scripts

```bash
# Enroll voter faces (pre-election)
python scripts/enroll_voters.py --csv voters.csv --images ./face_images/

# Enroll worker faces
python scripts/enroll_workers.py --csv workers.csv --images ./worker_images/

# Post-election hash chain audit
python scripts/verify_hash_chain.py --output audit_report.json
```

---

## Anomaly Flags

| Flag | Trigger |
|------|---------|
| `FLAG_GPS_VIOLATION` | Worker >500m from assigned booth at login |
| `FLAG_IMPOSSIBLE_MOVEMENT` | Worker at 2 booths >10km apart within 10min |
| `FLAG_FACE_DRIFT` | Similarity score drops on re-auth |
| `FLAG_TURNOUT_DEVIATION` | Actual vs ML-predicted turnout diff >15% for 30min |
| `FLAG_ABNORMAL_VOTE_RATE` | Votes/min significantly above baseline |
| `FLAG_DUPLICATE_ATTEMPT` | `has_voted=TRUE` voter attempts re-vote |
| `FLAG_LIVENESS_FAIL` | MiniFASNet detects photo/video replay |
| `FLAG_BOOTH_OFFLINE` | Heartbeat missed for >2 min |

---

## Monitoring

- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3000` (admin / matsetu_grafana)
- **Celery Flower**: `http://localhost:5555`
- **MinIO Console**: `http://localhost:9001`

---

## Troubleshooting

### 1. Database Connection Failures
If the FastAPI service cannot connect to PostgreSQL, ensure the `POSTGRES_PASSWORD` in `.env` matches the one in `docker-compose.yml` and the database container is healthy.

### 2. Face Matching Slowdown
High latency in face matching usually indicates Qdrant is under heavy load or the indices are not optimized. Check Qdrant metrics at `localhost:6333/dashboard`.

### 3. SMS Not Received
Check the Celery logs for `SMS_DELIVERY_FAILED` flags. If using Twilio, ensure credits are available. Fallback to thermal print (R8) if necessary.

### 4. RLS Policy Errors
If you see `permission denied for table`, re-run the RLS policy script:
```bash
docker exec -i matsetu_postgres psql -U matsetu -d matsetu < infra/rls_policies.sql
```

---

## License

Election Commission of India (ECI) — Internal Use Only  (EDU-purpose only) 
Platform: MatSetu v1.0 | All-India Edition
