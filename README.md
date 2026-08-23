# Full Stack Litestar Template

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://python.org)
[![Litestar](https://img.shields.io/badge/Framework-Litestar%20v2.18-8A2BE2.svg)](https://litestar.dev)
[![Granian](https://img.shields.io/badge/ASGI%20Server-Granian%20%28Rust%29-orange.svg)](https://github.com/emmett-framework/granian)
[![Podman](https://img.shields.io/badge/Containers-Rootless%20Podman%205.x-892CA0.svg)](https://podman.io)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2016%20%2B%20TimescaleDB%20%2B%20pgvector-336791.svg)](https://www.postgresql.org)
[![Valkey](https://img.shields.io/badge/Cache-Valkey%208.x-red.svg)](https://valkey.io)
[![PgBouncer](https://img.shields.io/badge/Pooler-PgBouncer%201.22-green.svg)](https://www.pgbouncer.org)
[![TypeScript](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite%20%2B%20TypeScript-3178C6.svg)](https://www.typescriptlang.org)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

> A production-grade, enterprise-ready full-stack platform built with **Litestar**, **Granian (Rust)**, **Advanced Alchemy**, **TimescaleDB + pgvector**, **Valkey 8**, **PgBouncer**, and **Rootless Podman Quadlets**. Engineered for extreme concurrency, clean architecture boundaries, zero-copy serialization, and resilience.

---

## Technology Stack and Features

- ⚡ [**Litestar**](https://litestar.dev) for the Python ASGI backend API.
  - 🧰 [Advanced Alchemy](https://docs.advanced-alchemy.litestar.dev) and [SQLAlchemy 2.0](https://www.sqlalchemy.org) for async ORM and repository pattern.
  - 🔍 [Pydantic v2](https://docs.pydantic.dev) and [msgspec](https://jcristharif.com/msgspec/) for high-performance data validation and zero-copy JSON serialization.
  - 💾 [PostgreSQL 16](https://www.postgresql.org) with [TimescaleDB](https://www.timescale.com) hypertables and [pgvector](https://github.com/pgvector/pgvector) embeddings.
  - 🏊 [PgBouncer](https://www.pgbouncer.org) connection pooler gateway for high-concurrency transaction scaling.
- 🚀 [React](https://react.dev) for the frontend.
  - 🧩 Integrated into the container mesh and reverse-proxied by Traefik on a unified origin.
  - 💃 Using TypeScript, hooks, [Vite](https://vitejs.dev), and modern frontend tooling.
  - 🎨 [Tailwind CSS](https://tailwindcss.com) and shadcn/ui components.
  - 🤖 Automatically generated frontend client with [@hey-api/openapi-ts](https://heyapi.dev).
  - 🦇 Dark mode and light mode support.
- 🐋 [Rootless Podman](https://podman.io) & [Docker Compose](https://www.docker.com) for container orchestration and Quadlet deployment.
  - 📞 [Traefik v3](https://traefik.io) as reverse proxy with automatic edge routing.
- 🔒 Secure password hashing (Argon2 / Passlib) by default.
- 🔑 JWT (JSON Web Token) authentication with Valkey blocklist revocation.
- 🛡️ Row-Level Security (RLS) transaction locals and Optimistic Concurrency Control (OCC).
- ⚡ In-memory caching and sliding-window rate limiting via [Valkey 8](https://valkey.io).
- ⚙️ [SAQ](https://github.com/tobymao/saq) async distributed worker & cron task scheduler on Valkey.
- 📦 Transactional Outbox pattern and Dead Letter Queue (DLQ) relay.
- 📬 [Mailpit](https://mailpit.axllent.org) for local email testing during development.
- ✅ Hermetic tests with [Pytest](https://pytest.org) (80/80 passing tests).
- 📖 Interactive OpenAPI 3.1 documentation ([Swagger UI](http://localhost:8000/docs/swagger) and [Scalar UI](http://localhost:8000/docs/scalar)).

---

## Screen Previews

<!-- Screen Preview Placeholder -->
<p align="center">
  <img src="docs/assets/dashboard-preview.png" alt="Dashboard Preview" width="800"/>
</p>

### Dashboard Login
<p align="center">
  <img src="docs/assets/login-preview.png" alt="Login Preview" width="800"/>
</p>

### Dashboard - Dark Mode
<p align="center">
  <img src="docs/assets/dashboard-dark.png" alt="Dashboard Dark Mode" width="800"/>
</p>

### Interactive API Documentation
<p align="center">
  <img src="docs/assets/docs-preview.png" alt="API Documentation" width="800"/>
</p>

---

## Feature Matrix

| Feature | Implementation | Description |
| :--- | :--- | :--- |
| **Authentication & RBAC** | JWT + Argon2 + Valkey Revocation | OAuth2 Password flow (JSON & form-data), bearer token revocation, Superadmin RBAC |
| **Data Persistence** | PostgreSQL 16 + Advanced Alchemy | Async SQLAlchemy 2.0 repositories, automatic migrations with Alembic |
| **Time-Series Analytics** | TimescaleDB Hypertables | Automated partitioning, compression policies (`> 7 days`), data retention policies |
| **AI Semantic Search** | pgvector + Reciprocal Rank Fusion | Hybrid HNSW cosine distance vector indexing + `pg_trgm` lexical ranking |
| **In-Memory Caching** | Valkey 8 | Session cache, hot-path lookup, token blocklists |
| **Rate Limiting** | Sliding-Window Middleware | Dual-tier sliding window rate limiting with atomic Valkey Lua scripts |
| **Row-Level Security** | PostgreSQL Session Context | Transaction-local tenant & role isolation (`app.current_user_id`, `app.current_tenant_id`) |
| **Background Tasks** | SAQ Distributed Worker | Async job queue, periodic cron schedules, retry policies, zombie recovery |
| **Guaranteed Delivery** | Transactional Outbox & DLQ | Atomic event persistence with sweep relay CLI and Dead Letter Queue recovery |
| **Edge Routing** | Traefik v3 Reverse Proxy | Unified routing for `/api/v1/*`, `/docs/*`, `/metrics`, and frontend SPA `/*` |
| **Public Ingress** | Cloudflare Zero Trust Tunnel | Containerized `cloudflared` tunnel without exposing public host ports |

---

## Quickstart Guide

Get the full-stack application up and running locally in under 2 minutes:

```bash
# 1. Build container images
make build

# 2. Start the core container mesh in background
make up

# 3. Apply database migrations
make migrate

# 4. Seed initial superuser account
make seed

# 5. Tail live container logs
make logs
```

The application is now accessible at:
- **Frontend Application:** [http://localhost:8000/](http://localhost:8000/)
- **Interactive Swagger UI:** [http://localhost:8000/docs/swagger](http://localhost:8000/docs/swagger)
- **Scalar Documentation:** [http://localhost:8000/docs/scalar](http://localhost:8000/docs/scalar)
- **Health Check Probe:** [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Mailpit Email UI:** [http://localhost:8025](http://localhost:8025)

---

## Default Credentials

| Service | Access URL | Email / Username | Default Password | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Web App** | [http://localhost:8000/](http://localhost:8000/) | `admin@platform.internal` | `AdminSecurePassword2026!` | Configurable in `.env` / `FIRST_SUPERUSER_EMAIL` |
| **Swagger UI Auth** | [http://localhost:8000/docs/swagger](http://localhost:8000/docs/swagger) | `admin@platform.internal` | `AdminSecurePassword2026!` | Authorize via OAuth2 Password Bearer |
| **Scalar Docs** | [http://localhost:8000/docs/scalar](http://localhost:8000/docs/scalar) | `admin@platform.internal` | `AdminSecurePassword2026!` | Interactive REST testing |
| **PostgreSQL DB** | `localhost:5432` | `app_user` | `secure_dev_password` | Database: `app_db` |
| **PgBouncer Pooler** | `localhost:6432` | `app_user` | `secure_dev_password` | Database: `app_db` (Transaction Mode) |
| **Mailpit Web UI** | [http://localhost:8025](http://localhost:8025) | *None* | *None* | Local SMTP port: `1025` |
| **Traefik Dashboard**| [http://localhost:8080](http://localhost:8080) | *None* | *None* | Dev-only dashboard on port `8080` |

---

## Backend Development

Backend documentation and developer workflow: [backend/README.md](./backend/README.md).

Includes Granian ASGI worker configuration, Alembic database migrations (`make migrate`), pytest test suite execution (`make test`), and OpenAPI schema export workflows (`make frontend-sync`).

## Frontend Development

Frontend documentation and development setup: [frontend/README.md](./frontend/README.md).

Includes Vite development server commands, Tailwind CSS theme configuration, Hey-API typed client generation, and production build testing (`make frontend-build`).

---

## Verification & Quality Gates

Run the complete QA verification gate across the entire project:

```bash
# Run Ruff linter and formatter check
make lint

# Run isolated transactional Pytest suite (80/80 passing)
make test

# Export OpenAPI schema & generate typed TypeScript fetch client
make frontend-sync

# Verify zero drift between backend schema and frontend client bindings
make check-client-drift

# Build production frontend bundle
make frontend-build
```

---

## Complete Documentation Index

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

## License

The Full Stack Litestar Template is licensed under the terms of the MIT License. See [LICENSE](LICENSE) for details.

