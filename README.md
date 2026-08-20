# LiteForge / Enterprise Platform

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://python.org)
[![Litestar](https://img.shields.io/badge/Framework-Litestar%20v2.18-8A2BE2.svg)](https://litestar.dev)
[![Granian](https://img.shields.io/badge/ASGI%20Server-Granian%20%28Rust%29-orange.svg)](https://github.com/emmett-framework/granian)
[![Podman](https://img.shields.io/badge/Containers-Rootless%20Podman%205.x-892CA0.svg)](https://podman.io)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2016%20%2B%20TimescaleDB%20%2B%20pgvector-336791.svg)](https://www.postgresql.org)
[![Valkey](https://img.shields.io/badge/Cache-Valkey%208.x-red.svg)](https://valkey.io)
[![PgBouncer](https://img.shields.io/badge/Pooler-PgBouncer%201.22-green.svg)](https://www.pgbouncer.org)
[![TypeScript](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite%20%2B%20TypeScript-3178C6.svg)](https://www.typescriptlang.org)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

> A production-grade, enterprise-ready full-stack scaffolding platform built with **Litestar**, **Granian (Rust)**, **Advanced Alchemy**, **TimescaleDB + pgvector**, **Valkey 8**, **PgBouncer**, and **Rootless Podman Quadlets**. Engineered for extreme concurrency, strict clean architecture boundaries, zero-copy serialization, and resilience.

---

## 🚀 System Highlights

- **Rust-Powered Ingress & ASGI Engine:** Powered by Granian and Traefik v3 cleartext HTTP/2 (`h2c`) reverse proxy with automated edge header forwarding.
- **Zero-Copy Serialization:** Uses `msgspec` Structs for lightning-fast JSON parsing and domain payload encoding with zero memory overhead.
- **TimescaleDB & Hybrid Semantic Search:** Automated hypertable partitioning, compression policies (`> 7 days`), data retention (`> 90 days`), combined with `pg_trgm` lexical scoring and `pgvector` HNSW cosine distance via Reciprocal Rank Fusion (RRF).
- **Asynchronous Background Processing:** SAQ distributed worker processes with Valkey-backed heartbeats, cron task scheduling, and automatic zombie recovery.
- **Transactional Outbox & DLQ:** Atomic database event persistence with automatic background relay sweeps and Dead Letter Queue (DLQ) replay CLI.
- **Enterprise Resilience Layer:** Idempotency-Key ASGI middleware, three-stage health probes (`/health/live`, `/health/ready`, `/health/startup`), circuit breaker state machine, and Prometheus metrics exposition (`/metrics`).
- **Strict Superadmin RBAC & OAuth2:** Password exchange supporting both JSON and form-data, JWT bearer token revocation via Valkey blocklists, and interactive Swagger UI / Scalar authorization.
- **Cloudflare Zero Trust Edge Ingress:** Outbound containerized tunnel (`cloudflared`) allowing public ingress without opening host firewall ports.
- **Rootless Podman Control Plane:** Non-root execution (`UID 10001`), SELinux volume relabeling (`:z` / `:Z`), and zero-pollution transactional testing.

---

## 📦 Port & Service Matrix

| Service | Container Name | Internal Port | Host Port | Routing / Access Point |
| :--- | :--- | :--- | :--- | :--- |
| **Traefik Edge Router** | `traefik` | `80`, `8080` | `8000:80`, `8080:8080` | `http://localhost:8000` (Gateway), `http://localhost:8080` (Dashboard) |
| **Litestar API Engine** | `api_app` | `8000` | Internal | Proxied via Traefik at `/api/v1/*`, `/docs/*`, `/health/*`, `/metrics` |
| **Frontend UI (Dev)** | `frontend_dev` | `5173` | Internal | Proxied via Traefik at `/*` (Vite HMR Dev-Server) |
| **SAQ Background Worker**| `worker_app` | None | None | Internal event queue consumer via Valkey |
| **PgBouncer Pooler** | `pgbouncer_pool`| `6432` | `6432` | `localhost:6432` (High-concurrency transaction pool) |
| **PostgreSQL + TimescaleDB**| `postgres_db` | `5432` | `5432` | `localhost:5432` (Direct migration & DDL access) |
| **Valkey In-Memory Cache** | `valkey_cache` | `6379` | `6379` | `localhost:6379` (Sessions, hot-path cache, task queues) |
| **Mailpit Mock SMTP** | `mailpit` | `1025`, `8025` | `1025`, `8025` | `http://localhost:8025` (Web UI), `localhost:1025` (SMTP) |
| **Cloudflare Zero Trust** | `cloudflared_tunnel`| None | None | Outbound secure edge tunnel to Cloudflare |

---

## 🚀 Quickstart: Generate a New Service in 60 Seconds

Bootstrap a production-ready application directly from this GitHub template repository:

### 1. Prerequisites
Ensure you have [Copier](https://copier.readthedocs.io/), [Podman](https://podman.io/) (or Docker), and `make` installed:
```bash
pipx install copier   # or: uv tool install copier
```

### 2. Generate Your Project
Run Copier directly against the Git repository URL:
```bash
copier copy gh:le-patrice/granite-stack my-new-service
```
Follow the interactive CLI prompts to select your project name, target ports, and optional infrastructure layers (TimescaleDB, pgvector, Valkey, PgBouncer, Cloudflare Tunnels, Frontend).

### 3. Start the Stack (Podman Default)
Navigate into your generated project and launch the container mesh:
```bash
cd my-new-service

# 1. Boot all core mesh services in background
make up

# 2. Apply database migrations & seed initial superuser
make migrate
make seed

# 3. Run zero-pollution transactional tests
make test
```

### 4. Access Points
- **Interactive Swagger UI:** [http://localhost:8000/docs/swagger](http://localhost:8000/docs/swagger)
- **Scalar API Docs:** [http://localhost:8000/docs/scalar](http://localhost:8000/docs/scalar)
- **Frontend Application:** [http://localhost:8000/](http://localhost:8000/)
- **Traefik Gateway Dashboard:** [http://localhost:8080/dashboard/](http://localhost:8080/dashboard/)
- **Mailpit Email Inspection:** [http://localhost:8025](http://localhost:8025)

---

## ⚡ Direct Repository Quickstart (Rootless Podman Default)

### 1. Boot the Container Mesh
```bash
# Start all services in the background (Podman default, Docker compatible)
make up
```

### 2. Apply Migrations & Seed Admin
```bash
# Run Alembic migrations inside the running container (TimescaleDB & Outbox)
make migrate

# Provision initial superuser from .env settings
make seed
```

### 3. Run Automated Tests
```bash
# Execute isolated transactional pytest suite inside container (65+ tests)
make test
```

### 4. Interactive API Documentation
Open your browser to explore and execute API requests:
- **Swagger UI:** [http://localhost:8000/docs/swagger](http://localhost:8000/docs/swagger)
- **Scalar UI:** [http://localhost:8000/docs/scalar](http://localhost:8000/docs/scalar)
- **OpenAPI 3.1 JSON Schema:** [http://localhost:8000/docs/openapi.json](http://localhost:8000/docs/openapi.json)
- **Traefik Dashboard:** [http://localhost:8080/dashboard/](http://localhost:8080/dashboard/)
- **Mailpit Email Inspection:** [http://localhost:8025](http://localhost:8025)

---

## 🛠️ Common Control Plane Commands

```bash
make up               # Boot entire container mesh in background
make up-dev           # Rebuild images with live development mounts
make down             # Stop and remove containers cleanly (preserves volumes)
make down-volumes     # Wipe containers and persistent database volumes (CAUTION)
make logs SERVICE=app # Stream live logs for a specific service
make worker           # Start SAQ background worker container
make worker-logs      # Tail live logs from distributed background workers
make health           # Check deep dependencies readiness (/health/ready)
make metrics          # Probe Prometheus scrapable metrics stream (/metrics)
make outbox-relay     # Execute pending transactional outbox event relay sweep
make dlq-replay       # Replay quarantined Dead Letter Queue events
make outbox-status    # Inspect pending outbox and DLQ event counts
make tunnel-status    # Inspect Cloudflare Zero Trust Tunnel container health
make tunnel-logs      # Tail live logs from Cloudflare Tunnel
make db-backup        # Dump timestamped compressed PostgreSQL backup in backups/
make frontend-sync    # Export OpenAPI schema & compile TypeScript fetch client
```

---

## 📚 Complete Documentation Index

| Documentation Guide | Description |
| :--- | :--- |
| **[Architecture Specification](docs/ARCHITECTURE.md)** | C4 Level 2 Container Diagram, Clean Architecture boundaries, data topology |
| **[Developer Handbook](docs/DEVELOPMENT.md)** | Local environment setup, adding new domain modules, testing runbook |
| **[Security & RBAC](docs/SECURITY_AND_RBAC.md)** | Argon2 KDF, JWT token flow & blacklisting, OAuth2 Password form login |
| **[Workers & Resilience](docs/WORKERS_AND_RESILIENCE.md)**| SAQ queues, Valkey Pub/Sub, Transactional Outbox, DLQ, Circuit Breakers |
| **[Production Deployment](docs/DEPLOYMENT.md)** | Systemd Quadlets, Cloudflare Tunnels, PgBouncer pooling, Traefik edge |
| **[Operational Runbook](docs/RUNBOOK.md)** | Disaster recovery, backups, troubleshooting namespace locks & pool exhaustion |
| **[Architecture Decisions (ADRs)](docs/decisions/)** | Michael Nygard ADR records (0001 through 0006) |

---

## 🧩 Architecture & Extensibility

| Resource | Description |
| :--- | :--- |
| **[Domain Blueprint](docs/DOMAIN_BLUEPRINT.md)** | **Canonical developer reference for scaffolding new domains, porting sub-projects, configuring ORM models, background tasks, and integrating React/Vite and Astro frontends with end-to-end type safety.** |

The Domain Blueprint covers:

- 📁 Canonical directory structure for any new feature domain (`orders`, `invoicing`, `nlp_pipelines`, `device_telemetry`)
- 🔩 Layer-by-layer implementation with complete production-ready code (schemas → interfaces → models → repository → controller)
- ⚡ Async execution matrix: when to use `BackgroundTask` vs SAQ Worker vs Transactional Outbox
- 🗄️ Alembic migration workflow with TimescaleDB hypertable and pgvector examples
- 🌐 Full-stack frontend integration: React/Vite and Astro with `@hey-api/openapi-ts` end-to-end type safety
- 🔄 Step-by-step checklist for porting standalone sub-projects (ML classifiers, FinTech services, etc.)
