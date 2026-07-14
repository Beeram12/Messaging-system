# Design Document — Notification Service

## High-Level Architecture

```
                          ┌─────────────────┐
                          │      Client      │
                          └────────┬─────────┘
                                   │ REST (X-API-Key)
                                   ▼
                     ┌─────────────────────────┐
                     │      FastAPI (API)       │
                     │  routers → services →    │
                     │       repositories        │
                     └────────┬─────────────────┘
                               │
              ┌────────────────┼─────────────────┐
              ▼                                   ▼
     ┌─────────────────┐               ┌───────────────────┐
     │   PostgreSQL     │               │      RabbitMQ       │
     │  notifications    │◄──────────────┤ notifications.      │
     │  user_preferences │   read status │   delivery (priority)│
     │  templates         │              │ notifications.retry  │
     │  notification_     │              │ notifications.       │
     │   attempts          │              │   delivery.dead_letter│
     │  rate_limit_buckets│              └──────────┬───────────┘
     └──────────▲──────────┘                          │
                │  status updates                      ▼
                │                          ┌─────────────────────┐
                └──────────────────────────┤   Worker (N replicas) │
                                            │  consume → call mock  │
                                            │  provider → update DB │
                                            │  → retry / dead-letter │
                                            └─────────────────────┘
```

The API and worker are independent processes that only share the Postgres database and the
RabbitMQ broker — either can be scaled, deployed, or restarted independently.

## Database Schema

| Table | Purpose | Key columns |
|---|---|---|
| `notifications` | One row per notification request; the source of truth for status | `id` (UUID PK), `user_id`, `channel`, `priority`, `status`, `body`, `subject`, `template_id`, `payload` (JSONB variables), `idempotency_key` (unique), `retry_count`, `created_at`/`sent_at`/`delivered_at` |
| `notification_attempts` | Audit trail — one row per delivery attempt | `notification_id` (FK), `attempt_number`, `status`, `error_message`, `created_at` |
| `user_preferences` | Per-user, per-channel opt-in/opt-out | composite PK `(user_id, channel)`, `enabled` |
| `templates` | Reusable message templates with `{{var}}` placeholders | `id` (PK), `subject`, `body` |
| `rate_limit_buckets` | Token-bucket state for per-user rate limiting; one row per user | `user_id` (PK), `tokens` (remaining, float), `last_refill_at` |

**Design notes:**
- `notifications.idempotency_key` has a unique index, so a duplicate key is rejected/detected at
  the DB level as a second line of defense even if the application-level check races.
- `status` transitions: `pending → queued → sent → delivered`, with `failed` (retries exhausted)
  and `skipped` (user opted out of that channel) as terminal side-branches.
- `notification_attempts` is append-only, giving full delivery history for debugging/support
  without overwriting the parent row — this is what `GET /notifications/{id}` returns.
- `rate_limit_buckets` implements a token-bucket rather than a sliding-window count: each user's
  bucket holds up to `rate_limit_per_hour` tokens (burst capacity), refilling continuously at
  `rate_limit_per_hour` tokens/hour. Each request costs 1 token; refill = `elapsed_seconds *
  (capacity / 3600)`, capped at `capacity`. The read (`SELECT ... FOR UPDATE`) + write happens in
  the same transaction as the notification insert, so the check and the deduction are atomic per
  user. This is simpler to reason about than a sliding window because there's no "wall" at a
  window boundary — tokens trickle back continuously instead of a burst becoming available all at
  once when a fixed window rolls over.
- Indexes on `user_id` and `status` support the two main read patterns: "history for a user" and
  future admin/monitoring queries filtering by status.

## Failure Handling & Retries

1. A message is published to RabbitMQ's `notifications.delivery` queue (priority-enabled,
   `durable=True`, messages persisted to disk) only **after** the notification row is committed
   to Postgres — so a crash between "write" and "publish" leaves a `queued`-status row that's
   safely re-publishable, rather than a lost message.
2. The worker acks a message only after successfully updating the notification's status in
   Postgres. If the worker crashes mid-processing, the unacked message is redelivered by
   RabbitMQ to another consumer.
3. On provider failure, the worker:
   - Records a `FAILED` attempt in `notification_attempts`.
   - Increments `retry_count`.
   - If `retry_count < 3`: republishes to a **per-delay TTL queue**
     (`notifications.retry.<delay_ms>ms`) that dead-letters back into the main delivery queue
     after the TTL expires. Delay = `5s * 2^retry_count` (5s, 10s, 20s) — exponential backoff
     without needing the RabbitMQ delayed-message plugin.
   - If retries are exhausted: status is set to `failed` and the message is published to
     `notifications.delivery.dead_letter` for manual inspection/alerting.
4. Poison messages (unparseable body, unexpected exception) are `nack`'d without requeue, so they
   don't loop forever consuming worker capacity.

## How the System Would Scale

- **API**: Stateless — horizontally scale behind a load balancer. The only shared state is
  Postgres and RabbitMQ, both of which support many concurrent connections.
- **Worker**: Multiple replicas can consume from the same queue concurrently; RabbitMQ handles
  fair dispatch via `basic_qos(prefetch_count=10)`. Adding replicas linearly increases delivery
  throughput as long as Postgres and the mocked providers (in reality, real provider rate limits)
  can keep up.
- **1000+ notifications/sec target**: The current design's likely bottleneck is the single
  Postgres write per notification (insert) plus a write per status transition (2-3 more updates).
  At high volume this is best addressed by:
  - Batching status-update writes (worker flushes updates in small batches instead of one
    commit per message).
  - Read replicas for the two GET endpoints, since history/status reads don't need
    read-your-writes consistency at that scale.
  - Partitioning `notifications` by time (e.g. monthly) once retention policy is defined, so
    indexes stay small and old data can be archived/dropped cheaply.
  - RabbitMQ itself comfortably handles tens of thousands of messages/sec on modest hardware;
    it is not expected to be the bottleneck.
- **Rate limiter**: see trade-off below — the current DB-backed token bucket (`SELECT ... FOR
  UPDATE` + `UPDATE` per check) would need to move to Redis (`INCR`/Lua-scripted bucket, O(1) per
  check, no row lock) before hitting real production throughput.

## Trade-offs

| Decision | Trade-off | Why acceptable here |
|---|---|---|
| DB-backed token bucket (row-locked read + update per request) instead of Redis | Slower than an in-memory bucket; the `SELECT ... FOR UPDATE` serializes concurrent requests from the *same* user (not across users) | Simpler stack (no Redis dependency), the token-bucket algorithm itself is easy to reason about/explain (burst capacity + continuous refill vs. a fixed window's "wall" at the hour boundary), and it's a documented, isolated upgrade path if throughput demands it — swapping the repository's storage layer for Redis wouldn't change the `RateLimiter` algorithm |
| "Delivered" set immediately after "sent" (mocked providers) | Doesn't model real async delivery receipts | Providers are explicitly mocked per the assignment; a real integration would add a webhook endpoint to move `sent → delivered` asynchronously (see Bonus: Webhook Support) |
| RabbitMQ TTL-queue trick for delayed retry instead of the delayed-message-exchange plugin | Creates one queue per distinct delay value (bounded: only 3 possible delays here) | Avoids depending on a non-default RabbitMQ plugin, keeping `docker-compose up` simple with the stock image |
| Idempotency key uniqueness enforced at DB (unique index) + app-level pre-check | Small race window between check and insert is still closed by the DB constraint, but a concurrent duplicate request would get a 500 rather than a clean "here's the existing one" | Acceptable for this scope; a stricter version would catch the `IntegrityError` and re-fetch, which is a natural follow-up |
| Single "priority" RabbitMQ queue (`x-max-priority`) vs. 4 separate queues | RabbitMQ priority queues don't give perfectly strict ordering under high load (some slop) | Simpler operationally (one queue, one consumer group) and "critical processed before low" is a soft ordering guarantee, not a hard real-time one, per the requirement wording |
