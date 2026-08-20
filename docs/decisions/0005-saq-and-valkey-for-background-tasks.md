# 5. Distributed Async Workers with SAQ and Valkey

Date: 2026-08-20

## Status

Accepted

## Context

Our application requires reliable asynchronous background processing for several core operations:
1. Transactional email dispatching (user verification, password resets).
2. Continuous time-series telemetry aggregations and metric rollups.
3. Periodic database maintenance (session pruning, expired token purges).
4. High-throughput dataset and analytics report exports.

Traditional background task queues like Celery introduce substantial operational complexity (RabbitMQ/Redis dependencies, heavy worker process memory footprints, and complex multi-threaded concurrency models). Alternatively, lightweight in-process background tasks (like `asyncio.create_task` or framework background tasks) run within the web request process lifecycle, creating risk of lost work during process restarts, deployments, or worker worker recycling.

## Decision

We adopt **SAQ (Simple Async Queue)** powered by our existing **Valkey 8** in-memory cluster:
1. **Zero Additional Broker Infrastructure:** Reuses the existing Valkey instance already used for token revocation and session caching.
2. **Pure AsyncIO Execution:** SAQ workers execute natively inside Python's async event loop without blocking subprocess forks or thread pools.
3. **Cron Job Scheduling:** Recurring jobs (hourly session pruning, 15-minute telemetry rollups) are declared directly in code via `saq.CronJob` objects.
4. **Heartbeat & Zombie Recovery:** Valkey-backed leases ensure that stalled tasks from dead workers are automatically reassigned and retried.

## Consequences

### Positive
- **Low Footprint:** 4 worker processes consume minimal memory while handling hundreds of concurrent async I/O tasks.
- **Unified Observability:** Background workers emit structured JSON logs via `structlog` and feed dead letters to our transactional DLQ.
- **Zero Celery Overhead:** No Erlang/RabbitMQ dependencies or complex kombu serialization overhead.

### Negative / Trade-offs
- Task payloads must be JSON-serializable (no raw Python pickle execution).
- Worker scaling requires horizontal container replication (`worker_app` instances).
