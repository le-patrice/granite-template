# Distributed Workers & Enterprise Resilience Specification

> **Classification:** Reliability Engineering & Asynchronous Infrastructure  
> **Status:** Active / Production Specification

---

## 1. SAQ Distributed Background Task Engine

Asynchronous task processing is powered by **SAQ (Simple Async Queue)** connected to the **Valkey 8** cluster.

### 1.1 Architecture & Task Declaration

All tasks and cron definitions reside in [`src/app/core/worker.py`](file:///home/pat/Business/LiteStar/backend/src/app/core/worker.py):

```python
from saq import CronJob, Queue
from app.core.settings import settings

queue = Queue.from_url(f"redis://{settings.VALKEY_HOST}:{settings.VALKEY_PORT}")

async def send_transactional_email(ctx: dict, *, to_email: str, subject: str, body: str) -> None:
    """Dispatches transactional email in background."""
    ...

async def process_telemetry_aggregation(ctx: dict, **kwargs) -> None:
    """Rolls up continuous aggregate metrics for IoT readings."""
    ...

async def prune_expired_sessions(ctx: dict) -> None:
    """Purges expired tokens and transient locks."""
    ...
```

### 1.2 Registered Cron Job Schedules

```python
worker_settings = {
    "queue": queue,
    "functions": [
        send_transactional_email,
        process_telemetry_aggregation,
        prune_expired_sessions,
        process_batch_export,
    ],
    "concurrency": 4,
    "cron": [
        CronJob(function=prune_expired_sessions, cron="0 * * * *"),       # Hourly
        CronJob(function=process_telemetry_aggregation, cron="*/15 * * * *"), # Every 15 min
    ],
}
```

### 1.3 Control Plane Worker Management
```bash
# Ensure SAQ worker container is active
make worker

# Stream live aggregated worker logs
make worker-logs
```

---

## 2. Transactional Outbox Pattern & Dead Letter Queue (DLQ)

To guarantee at-least-once message delivery without two-phase commit (2PC) locks, all domain event writes are persisted in the `outbox_events` table within the same transaction as state changes.

### 2.1 State Lifecycle & Transitions

```
[ Domain Mutation ]
       │ (Atomic DB Commit)
       ▼
 [ Status: PENDING ]
       │
   (Relay Sweep)
       ├───► Success ───► [ Status: PROCESSED ]
       │
       └───► Transient Error ───► Increment retry_count (< 3)
                   │
                   └───► Max Retries Exceeded (>= 3)
                               ├───► [ Status: DEAD_LETTER ]
                               └───► Insert into dead_letter_events (DLQ)
```

### 2.2 Dual-Mode Event Relay Architecture

The platform supports two complementary outbox relay mechanisms:

1. **Real-Time Event-Driven Daemon (`LISTEN/NOTIFY`):**
   A dedicated background daemon connects directly to PostgreSQL port `5432` (bypassing PgBouncer) and registers a persistent `LISTEN outbox_events_channel`. When a database transaction commits an outbox event, PostgreSQL fires a native `NOTIFY` trigger. The listener receives the payload and pushes it to Valkey Pub/Sub within 1–2 milliseconds.
   ```bash
   # Run the real-time event-driven outbox daemon
   make outbox-listen
   ```

2. **Periodic Safety-Net Sweep:**
   A scheduled batch sweep queries for any events remaining in `PENDING` status using `SELECT ... FOR UPDATE SKIP LOCKED`. This guarantees at-least-once delivery even if network hiccups briefly disconnect the real-time listener.
   ```bash
   # Trigger an immediate manual sweep of pending outbox events
   make outbox-relay
   ```

### 2.3 Outbox CLI & DLQ Replay Operations

```bash
# Inspect pending outbox events and quarantined DLQ items
make outbox-status

# Replay quarantined Dead Letter Queue events back into PENDING state
make dlq-replay
```

---

## 3. Zero-Copy Streaming Engine (RAM < 25MB)

For multi-gigabyte dataset exports, Parquet dumps, and continuous telemetry feeds, the platform provides the [`app.core.streaming`](file:///home/pat/Business/LiteStar/backend/src/app/core/streaming.py) module.

### 3.1 Streaming Mechanisms
- **`stream_file_chunks(path, chunk_size=65536)`:** Reads large on-disk artifacts in 64KB increments and streams directly through the ASGI response pipeline.
- **`stream_memoryview_chunks(data, chunk_size=65536)`:** Slices Python buffers using `memoryview` objects. This avoids duplicate string or bytes allocations in Python's garbage collector, keeping resident memory strictly bounded under 25MB regardless of total file size.
- **`stream_dataset_batches(query, session, batch_size=1000)`:** Executes cursor-streamed database reads via `yield_per()` without materializing whole result sets in memory.

```python
from litestar import get
from litestar.response import Stream
from app.core.streaming import stream_memoryview_chunks

@get("/api/v1/analytics/export")
async def export_dataset() -> Stream:
    # Streams zero-copy memoryview slices directly into ASGI chunks
    return Stream(
        stream_file_chunks("/tmp/analytics_dump.parquet"),
        headers={"Content-Disposition": 'attachment; filename="analytics.parquet"'},
        media_type="application/octet-stream",
    )
```

---

## 4. Idempotency Guard Middleware

The [`IdempotencyMiddleware`](file:///home/pat/Business/LiteStar/backend/src/app/core/idempotency.py) prevents duplicate execution on all mutating endpoints (`POST`, `PUT`, `PATCH`):

1. **Header Interception:** Reads `Idempotency-Key` from the incoming HTTP request.
2. **In-Flight Locking:** If another request with the same key is currently running, returns `409 Conflict` (`"A request with this Idempotency-Key is currently in-flight."`).
3. **Response Caching:** On completion, stores the HTTP status code, headers, and body in Valkey with a **24-hour TTL**.
4. **Replay Cache HIT:** On subsequent requests with the identical key:
   - Skips all controller, database, and repository execution.
   - Returns the cached response payload with `X-Cache-Idempotent: HIT`.

---

## 5. Circuit Breakers

The [`CircuitBreaker`](file:///home/pat/Business/LiteStar/backend/src/app/core/circuit_breaker.py) state machine wraps flaky downstream integrations (such as external SMTP or payment gateways):

```python
cb = CircuitBreaker(
    name="payment_gateway",
    failure_threshold=5,     # Trip to OPEN after 5 consecutive failures
    recovery_timeout=30.0,   # Wait 30 seconds before testing recovery
    half_open_max_trials=2,  # Gated trial requests in HALF_OPEN
)
```

- **Fail-Fast Protection:** When `OPEN`, calls fail immediately with `CircuitOpenException` without waiting for downstream timeouts.
- **Graceful Recovery:** Automatically resets to `CLOSED` after trial requests succeed in `HALF_OPEN`.

---

## 6. Three-Stage Health Probes & Prometheus Metrics

### 6.1 Health Probe Matrix

| Probe | Endpoint | Check Performed | Target Environment |
| :--- | :--- | :--- | :--- |
| **Liveness** | `GET /health/live` | Validates AsyncIO event loop responsiveness | Kubernetes / Podman liveness probe |
| **Readiness** | `GET /health/ready` | Deep dependency validation (`SELECT 1` on PostgreSQL + `PING` on Valkey) | Load balancer / Ingress traffic gate |
| **Startup** | `GET /health/startup`| Schema migration status & database revision baseline | Container startup initialization |

### 5.2 Scrapable Prometheus Metrics (`GET /metrics`)
Exposes standard Prometheus exposition format:
- `http_requests_total{method, path, status_code}`: Request counters.
- `http_request_duration_seconds{method, path}`: Latency percentile histograms.
- `db_connection_pool_active`: Active PostgreSQL connection count.
- `telemetry_ingest_records_total`: Ingested IoT record volume.
