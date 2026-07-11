# Notification Service

A backend service for sending notifications to users across multiple channels (Email, SMS, Push),
with priority-based delivery, retries, idempotency, rate limiting, and delivery tracking.

## Project Overview

The service exposes a REST API to enqueue notifications and query their status. A separate worker
process consumes notifications from a priority queue and delivers them through mocked
email/SMS/push providers, retrying failed deliveries with exponential backoff before giving up.

Core capabilities:
- Multi-channel delivery: email, SMS, push (each mocked — see [Technical Constraints](#assumptions))
- Per-user, per-channel opt-in/opt-out preferences
- Four priority levels (`critical`, `high`, `normal`, `low`) processed in priority order
- `{{variable}}` template substitution
- Delivery status tracking (`pending → queued → sent → delivered`, or `failed` / `skipped`)
- Automatic retry with exponential backoff, max 3 attempts, then dead-lettered
- Idempotency keys to prevent duplicate sends on client retries
- Per-user rate limiting (default: 100/hour)
- Structured JSON logging throughout

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | Required by the assignment |
| API framework | FastAPI | Async, Pydantic-based validation, automatic OpenAPI/Swagger docs generation for free |
| Database | PostgreSQL (via SQLAlchemy 2.0 + `psycopg3`) | Relational data (notifications, preferences) with clear consistency needs (idempotency keys, rate-limit counting); preferred by the assignment |
| Queue | RabbitMQ | Needs per-message priority, ack/nack semantics, and dead-lettering — RabbitMQ supports all of this natively (`x-max-priority`, DLX, TTL-based delayed retry) without extra infrastructure. Kafka is a better fit for high-volume append-only event streams, not per-task work queues with retry/priority semantics |
| Migrations | Plain `.sql` files + a small custom runner (`migrations/run_migrations.py`) | One file per table, applied in filename order; a `schema_migrations` table tracks what's already run. No ORM-diffing "magic" — every migration is exactly the SQL that will execute, reviewable in a PR like any other code |
| Worker | Standalone Python process (`worker/consumer.py`) | Decouples ingestion (API) from delivery (worker), so either can scale independently |
| Logging | `structlog` | Structured JSON logs with standard levels (INFO/WARNING/ERROR), suitable for log aggregation |
| Testing | `pytest` + `httpx`/`TestClient` | Standard Python testing stack; integration tests run against a real Postgres instance for fidelity |
| Containerization | Docker + docker-compose | Bonus requirement; also the easiest way to run Postgres + RabbitMQ locally |

## Architecture

See [DESIGN.md](DESIGN.md) for the full architecture diagram, schema design, and scaling discussion.

In short:

```
Client → POST /notifications → API (FastAPI)
                                   │
                    validate, dedupe, check prefs/rate-limit
                                   │
                          write to Postgres (status=queued)
                                   │
                          publish to RabbitMQ (priority queue)
                                   │
                                   ▼
                     Worker (consumer) ← ← ← (N replicas)
                                   │
                    call mocked provider (email/sms/push)
                                   │
                pass → status=delivered   fail → retry w/ backoff (max 3)
                                                   │
                                          exhausted → status=failed, dead-lettered
```

## Setup Instructions (Local Development)

### Prerequisites
- Docker and Docker Compose (recommended path)
- OR Python 3.11+, a local PostgreSQL instance, and a local RabbitMQ instance

### Option A: Docker Compose (recommended)

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, RabbitMQ, runs migrations (`migrate` one-shot service), then starts the API
(port 8000) and two worker replicas.

- API: http://localhost:8000
- Interactive API docs (Swagger UI): http://localhost:8000/docs
- RabbitMQ management UI: http://localhost:15672 (guest/guest)

### Option B: Run locally without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start Postgres + RabbitMQ only, via Docker:
docker compose up -d postgres rabbitmq

cp .env.example .env
python -m migrations.run_migrations

# Terminal 1
uvicorn app.main:app --reload

# Terminal 2
python -m worker.consumer
```

### Authentication

All endpoints (except `/health`) require an `X-API-Key` header. The default local key is
`dev-local-api-key` (see `.env.example`). This is a placeholder — see
[Assumptions](#assumptions).

### Example request

```bash
curl -X POST http://localhost:8000/notifications \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-api-key" \
  -d '{
    "user_id": "user-123",
    "channel": "email",
    "priority": "high",
    "body": "Hello, your order has shipped.",
    "idempotency_key": "order-987-shipped"
  }'
```

## API Documentation

Full interactive OpenAPI 3.0 docs are auto-generated by FastAPI and served at `/docs`
(Swagger UI) and `/redoc` when the app is running. The raw spec is at `/openapi.json`.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/notifications` | Enqueue a new notification |
| `GET` | `/notifications/{id}` | Get a notification's status and attempt history |
| `GET` | `/users/{userId}/notifications` | Paginated notification history for a user |
| `POST` | `/users/{userId}/preferences` | Set per-channel opt-in/opt-out preferences |
| `GET` | `/users/{userId}/preferences` | Get current preferences (defaults to all-enabled) |
| `GET` | `/health` | Liveness check (no auth) |

## Running Tests

Tests need a running Postgres instance (the test suite creates/drops its own
`notifications_test` database automatically).

```bash
docker compose up -d postgres rabbitmq
source .venv/bin/activate
pip install -r requirements.txt

pytest                                   # run all tests
pytest tests/unit                        # unit tests only (business logic)
pytest tests/integration                 # integration tests only (API + DB)
pytest --cov=app --cov=worker --cov-report=term-missing   # with coverage
```

34 tests covering: template rendering, retry/backoff math, priority ordering, idempotency,
opt-out handling, rate limiting, worker retry/dead-letter behavior, and all API endpoints
(success paths, validation errors, 404s, auth).

## Assumptions

Per the assignment's suggestion to document ambiguous decisions:

1. **Authentication**: A single static API key (`X-API-Key` header) stands in for what would be
   real auth/API-gateway integration in production. Good enough to demonstrate the concept
   without building a full auth system.
2. **User data**: Only `user_id` (an opaque string) is stored; no user service/profile exists.
   Contact info (actual email address, phone number, device token) is assumed to be resolved by
   the mocked provider layer or a separate user service — out of scope here.
3. **Providers are mocked**: `app/services/providers.py` simulates each channel with a ~10%
   random failure rate (to exercise the retry path) and no real network calls. Swapping in real
   providers means implementing `NotificationProvider.send()` for each channel.
4. **"Delivered" status**: Since providers are mocked, there's no real delivery webhook/callback.
   The worker marks a notification `delivered` immediately after a successful `sent`. A production
   integration would keep the status at `sent` until an async delivery receipt/webhook arrives.
5. **Templates**: Stored in Postgres (`templates` table) rather than in-memory, so they survive
   restarts and can be managed without redeploying. No template CRUD API was requested, so
   templates are currently seeded directly (e.g. via a DB session or a future admin endpoint).
6. **Rate limiting**: Implemented as a DB-backed token-bucket (one `rate_limit_buckets` row per
   user, storing remaining tokens + last refill time) rather than a Redis-backed bucket, since
   Redis wasn't part of the chosen stack for this build. This is documented as a trade-off in
   [DESIGN.md](DESIGN.md).
7. **Idempotency scope**: The idempotency key is unique per notification row (not scoped per
   user), matching "duplicate requests with the same idempotency key" in the spec. Callers should
   generate keys that are already unique per logical operation (e.g. `order-987-shipped`).
8. **Priority queue semantics**: RabbitMQ's native `x-max-priority` queue feature is used (10
   priority levels internally, mapped from the 4 external levels) rather than 4 separate queues,
   to keep a single consumer able to serve all priorities with less operational overhead.
