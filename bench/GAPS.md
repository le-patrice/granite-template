# bench/GAPS.md — Phase 1 (architecture) + Phase 2 (gap audit)

Status: **static analysis only.** Nothing has been run, so there are no measured numbers yet.
Every impact figure below is `[ESTIMATED]`. Items that need a runtime profile, an EXPLAIN plan or a
metric to confirm are listed under **Hypotheses**, not Findings.
Repo: `LiteStar` (Copier template) at the `main` HEAD `12f8e8f`. Branch: `bench/fixes`.
Host (read-only probe): 8 cores, 14 GB RAM (about 1.2 GB free at probe time), kernel 7.0.0-38, Podman 5.7.0, Go 1.27.1 (host), Python 3.14.4 (host; the image uses 3.11-slim).
Not yet pinned, to be recorded in Phase 3: Postgres/Timescale/Valkey/PgBouncer/Granian/Traefik versions. Note that `edoburu/pgbouncer:latest`, `mailpit:latest` and `uv:latest` are unpinned in the repo.

Scope decisions (from the user): benchmark a Copier-rendered throwaway instance of this template; scaled-down dataset (10k users, 1M telemetry rows, 10-minute soak, labelled as scaled-down); local tools only; stop for review after Phase 2.

---------------------------------------------------------------------------------------------------

## PHASE 1 — Architecture map

### Request path (hybrid)
```
client -> Traefik :80 (traefik-dev.yml)
   |-- /api/v1/telemetry/ingest (priority 100) -> Go ingest :8001      [cors, secure-headers ONLY]
   |-- /api/*  (priority 66)  -> Granian/Litestar :8000                [cors, secure-headers, global-ratelimit 150/min/IP]
   |-- /health,/metrics       -> Litestar
   `-- /*                     -> frontend
Litestar middleware order (app/__init__.py:133-141): RequestLogging -> CSRFOrigin -> PrometheusMetrics
   -> Idempotency -> SlidingWindowRateLimit -> route guard (JWTAuthGuard) -> handler
JWTAuthGuard (auth_guard.py:30-89): decode HS256 JWT -> Valkey GET revocation(jti) -> set contextvars (user/tenant/role)
DB session (database.py:84-107): after_begin hook runs `SELECT set_config(app.current_user_id|tenant_id|role, ..., true)`
   -> PgBouncer :6432 (transaction mode) -> Postgres/Timescale :5432
RLS: policies call current_setting('app.current_tenant_id') (0005, 0007); app_runtime role (0006) is the only non-bypass role.
Outbox: handlers insert outbox_events; SAQ cron `* * * * *` (worker.py:210) -> relay.process_sweep(batch 50) -> Valkey PUBLISH.
        LISTEN/NOTIFY daemon exists (relay.listen_and_relay) but only as `make outbox-listen`; it is NOT in the pod spec.
SAQ: `python -m saq app.core.worker.settings --workers 4`, concurrency 4 (worker.py:227).
Rate limiting: Traefik (150/min/IP, burst 50) AND Valkey Lua (120/min/IP api, 5/min login) -> double limiting on /api.
SSE: no SSE endpoint exists (see claim audit).
```

### README / sub-README performance claims
| # | Claim (source) | Status | Reasoning |
|---|---|---|---|
| C1 | "uvloop for 2x to 4x coroutine execution throughput" (README:42) | needs-benchmark | Generic uvloop claim; depends on workload. We only measure this stack, not uvloop vs asyncio. |
| C2 | Go bypass "Sub-microsecond edge bypass ... 25,000+ req/s and 14MB resident" (README:43) | **implausible (partly)** | A request that does JSON decode + a DB `COPY` round trip + a Valkey pipeline cannot be sub-microsecond; that is physically impossible over TCP. RPS and RSS need-benchmark. |
| C3 | "Zero-Copy Streaming ... Parquet/Arrow exports ... sub-25MB heap ceiling" (README:44) | **refuted by code** | No Parquet/Arrow dependency or code exists (grep: only a default string `"parquet"` at worker.py:154). `process_batch_export` loads `LIMIT batch_size` ORM rows into a list (worker.py:165-169) and only counts them. |
| C4 | Go ingest "115,000+ rows/sec (9.5x faster)" vs Python "~12,000 rows/sec" (services/telemetry-ingest/README:15) | needs-benchmark | Plausible for COPY, but it compares against the Python path that uses executemany (see G11), not an optimised Python path. |
| C5 | "~18 MB image", "12 ms cold start", "~15 MB idle / ~65 MB loaded" (ingest README:16-19) | needs-benchmark | Image size and startup are cheap to measure. |
| C6 | Python telemetry repo "reduces DB round-trips by ~1000x ... asyncpg sends this as one server round-trip" (telemetry_repository.py:5-6, 53-54) | needs-benchmark / likely overstated | The code uses `text()` + list of dicts, which is SQLAlchemy executemany, not one multi-VALUES statement. The docstring is inaccurate. |
| C7 | "Transactional Outbox ... guaranteed event delivery"; "effectively-once" | **refuted by code** (see G19) | Publish is fire-and-forget Pub/Sub and locks release after the first commit. |
| C8 | "Circuit breaker" resilience | **refuted by code (not wired)** | `circuit_breaker.py` has zero call sites outside its own module (grep). |
| C9 | PgBouncer "high concurrency" | needs-benchmark | Config mismatch noted in G09. |

### Go ingest bypass audit (main.go)
| Control | Python path | Go path | Gap |
|---|---|---|---|
| Authentication | JWTAuthGuard (telemetry_controller.py:39) | **none** (main.go:124); Traefik router has no auth middleware (traefik-dev.yml, `telemetry-ingest-router`) | **P0**: unauthenticated writes into the DB through the public edge |
| Tenant / RLS | none either (`telemetry_readings` has no `organization_id`, 0002) | none | design gap in both |
| Rate limit | Traefik + Lua | **none** (router lacks `global-ratelimit`) | unbounded write rate |
| Idempotency | middleware (global key, see G03) | none; `uuid.New()` per row, so retries duplicate rows | duplicates on retry |
| Body size / validation | Litestar default limit + msgspec | `json.NewDecoder(r.Body)` with no `MaxBytesReader`; no field validation | memory DoS |
| Backpressure | n/a | none (no bounded queue; 30 pool conns, then blocking) | latency collapse under overload |
| Graceful shutdown | Granian | `Shutdown(5s)` only; in-flight batches are synchronous, so little loss | OK |

---------------------------------------------------------------------------------------------------

## PHASE 2 — Findings (static evidence)

Columns: ID | layer | finding | evidence | impact [ESTIMATED] | effort | risk | applies to | priority.
Priority: P0 security/correctness, P1 high perf, P2 medium, P3 low.
"Impact" values are `[ESTIMATED]` from reasoning only and must be confirmed in Phase 5.

| ID | Layer | Finding | Evidence | Expected impact [ESTIMATED] | Effort | Risk | Applies | Pri |
|---|---|---|---|---|---|---|---|---|
| G01 | Go ingest / Traefik | Public unauthenticated + unthrottled write path | `main.go:124`; `config/traefik-dev.yml` `telemetry-ingest-router` middlewares = cors, secure-headers | Security; adding JWT verify costs about 10-30 us/req in Go | S-M | Low | hybrid | P0 |
| G02 | Go ingest | No body limit, no field validation, retries duplicate rows (random uuid PK, no dedup key) | `main.go:125,146`; `telemetry_repository.py:63` (`ON CONFLICT DO NOTHING` can never fire with random UUID PK `(id, recorded_at)`, 0002) | Prevents memory DoS and duplicate rows | S | Low | hybrid, Go-only | P0 |
| G03 | Idempotency | Key is global (`idempotency:{key}`), not scoped by tenant/user/method/path; check-then-set is non-atomic (GET at :60, SET at :82), so two concurrent requests both proceed; response body cached in full | `core/idempotency.py:55,60-82,117-129` | Fix to `SET NX` cuts 3 Valkey RTTs to 2 on mutating calls; closes cross-tenant replay | S | Low (behaviour change: key scoping) | both | P0 |
| G04 | RLS / DB role | Runtime connects as `app_user`, which is the image `POSTGRES_USER` (superuser, so RLS is bypassed even with FORCE). The guard only checks when `rolname == 'app_runtime'` | `platform-pod.yaml` `DATABASE_URL=...app_user...`; `app/__init__.py:112` | "RLS on" benchmarks are invalid unless run as `app_runtime`. Cost of RLS is unmeasured in the default config | S | Med (behaviour change) | both | P0 (verify `rolsuper` at runtime) |
| G05 | Rate limit / proxy trust | `CF-Connecting-IP` and `X-Forwarded-For` trusted unconditionally; Traefik `forwardedHeaders.insecure: true` | `rate_limit.py:42-46`, `logging.py:71-75`, `traefik-dev.yml` entryPoints.web | Rate limiter bypass by header spoofing | S | Low | both | P0 |
| G06 | Valkey / Lua | Script text sent with `EVAL` on every request; no `EVALSHA`/`register_script` | `rate_limit.py:109` | 5-10% of the RTT CPU for that call | S | Low | hybrid | P2 |
| G07 | Valkey RTTs | Up to 5 sequential Valkey RTTs per mutating request: revocation GET + rate-limit EVAL + idempotency GET + SET + final SET; nothing pipelined | `auth_guard.py:68`, `rate_limit.py:109`, `idempotency.py:60,82,129` | At about 0.1-0.3 ms each on loopback: 0.5-1.5 ms p50 added [ESTIMATED] | M | Low-Med | both | P1 |
| G08 | SQLAlchemy | Per-transaction RTTs: `pool_pre_ping` `SELECT 1` + `set_config` SELECT + the query + commit; the readiness probe pays all of them | `database.py:53-54,100-107`; `health_controller.py:52-60` | 1 read request = about 3-4 RTTs vs 1. Removing pre_ping saves 1 RTT (about 0.1-0.3 ms) | S-M | Low-Med | hybrid | P1 |
| G09 | Pooling | Pool arithmetic: 4 Granian workers x (pool 20 + overflow 10) = up to 120 client conns vs PgBouncer `DEFAULT_POOL_SIZE=25`; plus 4 SAQ processes; Go direct pool 30 bypasses PgBouncer; PG default `max_connections` 100 | `Containerfile` `--workers 4`; `settings.py:17-18`; `platform-pod.yaml` pgbouncer env; `main.go:52` | Queueing in PgBouncer under load; exact queue depth needs SHOW POOLS | S | Low | hybrid | P1 |
| G10 | PgBouncer / asyncpg | `statement_cache_size=0` disables asyncpg prepared statements; `edoburu/pgbouncer:latest` is unpinned so protocol-level prepared statement support (PgBouncer >= 1.21, `max_prepared_statements`) is unknown | `database.py:57`; `platform-pod.yaml` | If supported, saves parse/plan round trips; pending version check | S | Med | hybrid | P2 (Hypothesis until version pinned) |
| G11 | Telemetry (Python) | Bulk insert is SQLAlchemy `executemany` of N dicts (not COPY, not one statement); per-row `uuid4()` string and `datetime` conversion in Python; docstring claims "one round-trip" | `telemetry_repository.py:38-67` | At batch 1000, `unnest()` arrays or asyncpg `copy_records_to_table` is typically several x faster than executemany [ESTIMATED 2-5x] | M | Low | hybrid | P1 |
| G12 | Logging | Four log writers per request: Granian `--access-log`, `RequestLoggingMiddleware`, Traefik access log (`bufferingSize: 0`), plus DEBUG level and ConsoleRenderer when `DEBUG=True` (default); `RotatingFileHandler` writes synchronously on the event loop; Litestar `debug=settings.DEBUG` | `Containerfile` `--access-log`; `logging.py:21,32,53,84-120`; `settings.py:7`; `app/__init__.py:150`; `traefik-dev.yml` accessLog | 10-25% RPS on W1 [ESTIMATED] | S | Low | both | P1 |
| G13 | Granian | `--workers 4` hard-coded regardless of CPU limit; `--blocking-threads` unset; dev pod runs `--reload` (what `make up` uses), so a bench with `make up` is not production-like | `Containerfile`; `platform-pod.yaml` app command | Oversubscription under a 2-CPU limit | S | Low | hybrid | P1 |
| G14 | Auth | Unknown-email login returns before any Argon2 work, so it is a timing oracle for user enumeration; Argon2 runs on the default executor (up to cpu+4 concurrent hashes at ~64 MiB each, parameters to be verified) | `auth_controller.py:66-67`; `security.py:91-97` | Security (low) + memory ceiling on login bursts | S | Low | both | P2 |
| G15 | Pagination | `OFFSET` pagination with no upper bound on `limit` (default 100, unbounded max) | `user_repository.py` `list_all`; `users_controller.py:345` | O(offset) at deep pages; unbounded `limit` is a DoS vector | M | Med (API change) | both | P2 |
| G16 | RLS | `current_setting()` calls are not wrapped in `(SELECT ...)` and sit inside `OR` chains; tenant column is not leading in any composite index (single-column `organization_id` index only) | `0005_*.py` policy, `0007_*.py` policy; `users/models.py` | Possible per-row evaluation and index mismatch; **needs EXPLAIN** (Hypothesis H2) | M | Low-Med | both | P2 |
| G17 | Audit trigger | Row-level AFTER trigger does `to_jsonb(OLD)`+`to_jsonb(NEW)` into a hypertable on every user write | `0004_*.py` `process_audit_log` | Write amplification on W3 (about 1.5-2x write cost [ESTIMATED]) | M | Med (audit semantics) | both | P2 |
| G18 | TimescaleDB | Default 7-day chunk interval; no continuous aggregate (the aggregation job scans 24 h of raw rows and discards the result); a single-column `transformer_id` index is redundant with the composite index; random-UUID PK in a hypertable index | `0003_*.py` `create_hypertable`; `worker.py:94-117`; `0002_*.py` index comment + `telemetry/models.py` | Write amplification on ingest from the extra index; wasted CPU in the cron job | M | Low | both | P2 |
| G19 | Outbox | `mark_processed` commits per event, releasing `FOR UPDATE SKIP LOCKED` locks after the first event, so other relays can re-select the rest (duplicates). Publish happens before mark (at-least-once). Pub/Sub is fire-and-forget (lost when no subscriber). Cron cadence is 1/min; LISTEN daemon is not deployed. No backoff between retries; `retry_count<3` with no delay | `relay.py:52-74,153-184`; `worker.py:210` | Correctness (duplicates, loss). Latency up to 60 s [ESTIMATED] | M | Med | both | P1 |
| G20 | Streaming / SSE | W6 (SSE) and W7 (Parquet export) are **not implemented**; claim C3 is refuted. The harness can only benchmark them after they exist | grep results (see claim audit) | n/a | L | n/a | both | P2 (scope) |
| G21 | Valkey | Two separate clients (`valkey_store` and `get_valkey_pool`), neither with `max_connections` or `health_check_interval`; no `maxmemory`/policy on the container (default noeviction) while idempotency keys keep full response bodies for 24 h; transformer state is written with one command per transformer (not pipelined) | `valkey_service.py:27`; `cache.py:22`; `platform-pod.yaml` valkey-cache; `valkey_service.py:62-64` + `telemetry_controller.py:72` | Memory growth leading to write failures; N RTTs per ingest batch | S-M | Low | hybrid | P1 |
| G22 | Go ingest | Valkey pipeline runs synchronously (the `WaitGroup` adds nothing) with `context.Background()` (no timeout) so ingest latency is coupled to Valkey; stdlib `encoding/json`; per-row `[]any` + client uuid; no `GOMAXPROCS`/`GOMEMLIMIT`; no pprof; per-request `log.Printf`; `go.mod` 1.23 vs Containerfile 1.24 | `main.go:180-200,125,146,255`; `go.mod`; `Containerfile` | Latency and tail coupling; GC under container limits | S-M | Low | Go-only, hybrid | P1 |
| G23 | Traefik | Edge rate limit 150/min/IP will throttle any single-IP benchmark (about 2.5 req/s); no compression or timeouts middleware; access log unbuffered; `--accesslog.format=json` conflicts with file `common` | `traefik-dev.yml` global-ratelimit / accessLog; `platform-pod.yaml` traefik args | Benchmark must bypass or disable (record it); compression gap | S | Low | both | P2 |
| G24 | Podman | No `resources:` limits on any container (so no CPU throttling is possible or measurable, and there is no OOM containment) | `platform-pod.yaml` (no resources keys) | Needed for fair comparison (harness will add identical limits) | S | Low | both | P2 |
| G25 | Metrics | Unbounded label cardinality: any unmatched `/api/...` path that is not UUID/numeric is used raw as the `path` label | `metrics.py:97-106` | Memory leak in the Prometheus registry under scanner traffic | S | Low | both | P1 |
| G26 | Frontend delivery | `nginx.conf` sets a 1-year immutable cache on assets but no `gzip`/`brotli` directives found; bundle (earlier `make check` output, single run): JS 249.63 kB / 75.51 kB gzip, CSS 27.46 kB / 5.84 kB gzip [MEASURED once] | `frontend/nginx.conf:15-16` | Smaller transfers if compression is off | S | Low | hybrid | P3 |
| G27 | Circuit breaker | Module exists but has zero call sites, so the DB/Valkey failure paths are fail-open only in rate limit/idempotency, nothing for the DB | `core/circuit_breaker.py`; grep | Resilience gap; Phase 4 failure injection will confirm behaviour | M | Low | both | P2 |
| G28 | Readiness | `/health/ready` opens a DB session (set_config + SELECT 1) and a Valkey PING on every probe | `health_controller.py:52-75` | Probe cost on W1; add 1 s TTL cache | S | Low | both | P3 |

### Checklist A-R status
| | Layer | Status | Notes |
|---|---|---|---|
| A | Granian/Litestar | GAP | G12, G13. Event-loop lag, slow-callback and OpenAPI startup cost need runtime (H1). |
| B | msgspec | OK | `TelemetryRecord` is a `msgspec.Struct(gc=False)` (schemas.py). `Encoder`/`Decoder` are reused (valkey_service.py:34-35). Idempotency uses `json` (stdlib) for cache records (minor). Response caching/ETag absent (see R). |
| C | SQLAlchemy | GAP | G08, G09, G10, G11. N+1 / lazy loads: no relationships on hot paths found statically. Round-trip counts need runtime (H3). |
| D | Postgres | UNVERIFIED | No postgresql.conf overrides exist in the pod (statically verified). `shared_buffers`, `pg_stat_statements`, `auto_explain`, timeouts and vacuum need a live instance (H4). |
| E | RLS | GAP/UNVERIFIED | G04, G16. Cost needs EXPLAIN (H2). |
| F | TimescaleDB | GAP | G18. Ingest-rate vs chunk interval needs measurement. |
| G | PgBouncer | GAP/UNVERIFIED | G09, G10. Version and `SHOW POOLS` needed. |
| H | Valkey | GAP | G06, G07, G21. SLOWLOG / commandstats need runtime. |
| I | Auth cost | GAP | G14. Argon2 parameters and JWT verify cost to be measured (H5). |
| J | Go ingest | GAP | G01, G02, G22. CopyFrom is already used (OK). Batching/queue bounds absent. |
| K | Outbox/SAQ | GAP | G19. |
| L | SSE | N-A | Not implemented (G20). |
| M | Traefik | GAP | G05, G23. |
| N | Podman/OS | GAP/UNVERIFIED | G24. Pasta/loopback, `nr_throttled`, somaxconn and FD limits need runtime. |
| O | Observability | GAP | G12, G25. |
| P | Python runtime | UNVERIFIED | Image is python:3.11-slim. GC/allocator not tuned (H6). |
| Q | Frontend | GAP | G26. |
| R | Missing capabilities | GAP | No ETag/HTTP caching, request coalescing, bulk endpoints, load shedding, per-endpoint timeouts, read replicas; audit is synchronous (G17); breaker unwired (G27). |

---------------------------------------------------------------------------------------------------

## Hypotheses (no runtime evidence yet; will be confirmed or dropped in Phase 3)
- H1 Event-loop blocking: `RotatingFileHandler` and sync `jwt`/`json` work may add measurable loop lag at high RPS. Test: asyncio debug slow-callback + loop-lag metric.
- H2 RLS policy cost: `current_setting()` per row and `OR` chains may prevent index use or add per-row cost on list endpoints. Test: `EXPLAIN (ANALYZE, BUFFERS)` as `app_runtime` vs `app_user`, then retest with `(SELECT current_setting(...))` wrapping.
- H3 Round trips/request: expected 3-4 DB RTTs for a single read (G08). Test: `pg_stat_statements` calls per request.
- H4 Postgres defaults (shared_buffers 128 MB, no pg_stat_statements) limit W2/W4. Test: `SHOW`, `pg_stat_statements`.
- H5 Argon2 default parameters make login CPU-bound well below the 5/min rate limit; unknown parameters. Test: time `verify_password`.
- H6 GC/allocator tuning (`gc.freeze`, jemalloc) gives a small gain. Low priority.
- H7 Postgres unlogged/synchronous_commit settings on ingest are untouched; `synchronous_commit=off` for telemetry could raise W4 (behaviour change: durability).
- H8 Traefik adds measurable p99 overhead vs direct-to-app; test with and without the proxy.
- H9 Go-only gains will be mostly in RSS and startup, with smaller RPS gains on DB-bound workloads (W2, W4) because both stacks share the same Postgres limit. Cannot be asserted before Phase 6.

## Open items needing the user before Phase 3
1. Confirm the RAM plan: current free RAM is about 1.2 GB. The scaled-down dataset needs roughly 2-3 GB for Postgres, plus stack and load generator. Please close other apps, or reduce the container limits.
2. W6 (SSE) and W7 (Parquet export) do not exist in the code. Options: (a) mark them N/A, (b) implement minimal versions on `bench/fixes` so the claims can be measured. I recommend (a) for the first pass.
3. Tool install permission was granted for user-local installs; the harness will use `oha` for constant-rate load. Note that `oha -q` is open-loop-ish but not coordinated-omission-free; `k6` with `constant-arrival-rate` is the better fit. I will use `k6` if the binary is obtainable, otherwise `oha` and note the limitation.
