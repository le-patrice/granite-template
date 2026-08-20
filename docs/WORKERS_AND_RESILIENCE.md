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

### 2.2 Outbox CLI & DLQ Replay Operations

```bash
# Inspect pending outbox events and quarantined DLQ items
make outbox-status

# Trigger an immediate background sweep of pending outbox events
make outbox-relay

# Replay quarantined Dead Letter Queue events back into PENDING state
make dlq-replay
```

---

## 3. Idempotency Guard Middleware

The [`IdempotencyMiddleware`](file:///home/pat/Business/LiteStar/backend/src/app/core/idempotency.py) prevents duplicate execution on all mutating endpoints (`POST`, `PUT`, `PATCH`):

1. **Header Interception:** Reads `Idempotency-Key` from the incoming HTTP request.
2. **In-Flight Locking:** If another request with the same key is currently running, returns `409 Conflict` (`"A request with this Idempotency-Key is currently in-flight."`).
3. **Response Caching:** On completion, stores the HTTP status code, headers, and body in Valkey with a **24-hour TTL**.
4. **Replay Cache HIT:** On subsequent requests with the identical key:
   - Skips all controller, database, and repository execution.
   - Returns the cached response payload with `X-Cache-Idempotent: HIT`.

---

## 4. Circuit Breakers

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

## 5. Three-Stage Health Probes & Prometheus Metrics

### 5.1 Health Probe Matrix

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
