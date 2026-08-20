# 6. PgBouncer Connection Pooling for High-Concurrency Scaling

Date: 2026-08-20

## Status

Accepted

## Context

PostgreSQL relies on a process-based client model where each incoming TCP connection forks a dedicated backend operating system process consuming 5–10 MB of RAM. Under high traffic spikes (e.g. thousands of concurrent API requests, background task workers, and microservices), direct PostgreSQL connection spikes can trigger:
1. Connection exhaustion (`too many connections` errors).
2. High context-switching overhead on the database server.
3. Severe memory pressure and cache thrashing.

While SQLAlchemy's client-side connection pool (`AsyncEngine`) mitigates connection overhead within a single container, it does not manage connections globally across multiple distributed app and worker instances.

## Decision

We introduce **PgBouncer** in **Transaction Pooling Mode** as an optional, high-throughput connection gateway on port `6432`:
1. **Transaction Pooling (`POOL_MODE=transaction`):** Server connections are returned to the pool immediately upon completion of a transaction rather than holding connections for the entire client session duration.
2. **Extreme Concurrency:** A small pool of 25–50 physical PostgreSQL connections can service thousands of active client connections (`MAX_CLIENT_CONN=1000`).
3. **Transparent Drop-In Gateway:** Applications simply change `DATABASE_PORT` from `5432` to `6432` with zero code refactoring.
4. **Direct Port 5432 Reserved:** Migration tools (`alembic upgrade head`), DDL scripts, and administrative maintenance bypass PgBouncer and connect directly to port `5432` to preserve transactional DDL and session-level locks.

## Consequences

### Positive
- **Database CPU & Memory Protection:** Flat, predictable server connection counts regardless of upstream web traffic bursts.
- **Instant Response Times:** Connection establishment latency drops from tens of milliseconds to sub-millisecond local pool handoffs.

### Negative / Trade-offs
- Session-level PostgreSQL features (such as `LISTEN/NOTIFY`, temporary tables, and session advisory locks) cannot be used through PgBouncer in transaction pooling mode. Our architecture handles Pub/Sub via Valkey instead.
- Prepared statement caches must be managed with `statement_cache_size=0` in `asyncpg` when pooling across transactions.
