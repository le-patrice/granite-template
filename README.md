# Granite Platform

<p align="center">
  <em>Enterprise asynchronous platform powered by Litestar 2.x, Granian (Rust) + uvloop, React 19, TimescaleDB, PgBouncer, Valkey 8, Go Ingestion Bypass, and Rootless Podman Quadlets.</em>
</p>

<p align="center">
  <a href="https://github.com/le-patrice/granite-template/actions" target="_blank">
    <img src="https://img.shields.io/badge/CI-passing-emerald?style=flat-square" alt="CI Status" />
  </a>
  <a href="https://litestar.dev" target="_blank">
    <img src="https://img.shields.io/badge/Litestar-2.10-17485%25?style=flat-square&logo=python&logoColor=white" alt="Litestar" />
  </a>
  <a href="https://react.dev" target="_blank">
    <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
  </a>
  <a href="https://www.postgresql.org" target="_blank">
    <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  </a>
  <a href="https://valkey.io" target="_blank">
    <img src="https://img.shields.io/badge/Valkey-8.x-CC0000?style=flat-square&logo=redis&logoColor=white" alt="Valkey" />
  </a>
  <a href="https://traefik.io" target="_blank">
    <img src="https://img.shields.io/badge/Traefik-v3-24A1C1?style=flat-square&logo=traefikproxy&logoColor=white" alt="Traefik" />
  </a>
  <a href="https://podman.io" target="_blank">
    <img src="https://img.shields.io/badge/Podman-5.x_Quadlets-892CA0?style=flat-square&logo=podman&logoColor=white" alt="Podman" />
  </a>
</p>

---

<p align="center">
  <img src="docs/assets/dashboard-preview.png" alt="Platform Dashboard Light Mode" width="100%"/>
  <img src="docs/assets/dashboard-dark.png" alt="Platform Dashboard Dark Mode" width="100%"/>
</p>

---

## Architecture Highlights

* **Rust ASGI & uvloop Engine:** Built on [Litestar 2.x](https://litestar.dev) and powered by [Granian](https://github.com/emmett-framework/granian) with `uvloop` for 2x to 4x coroutine execution throughput.
* **Compiled Go Telemetry Bypass:** Sub-microsecond edge bypass microservice (`services/telemetry-ingest`) handling `POST /api/v1/telemetry/ingest` with 25,000+ req/s and a 14MB resident memory footprint.
* **Zero-Copy Streaming Engine:** Chunk-buffered streaming engine using Python `memoryview` for gigabyte-scale datasets and Parquet/Arrow exports maintaining a sub-25MB heap ceiling.
* **Modern Admin Dashboard:** React 19 + TypeScript + Vite with Tailwind CSS design tokens, telemetry monitors, and inline validation.
* **Turnkey Typed Client Generation:** Automated `@hey-api/openapi-ts` SDK pipeline exporting backend schemas to type-safe TypeScript fetch clients.
* **Dual-Tier Ingress & Rate Limiting:** Traefik v3 burst rate limiter coupled with an atomic Valkey Lua sliding-window limiter.
* **Multi-Engine Interactive OpenAPI Docs:** Scalar on `/docs`, Swagger UI on `/docs/swagger`, and Redoc on `/docs/redoc`.
* **Hybrid Relational & Time-Series Engine:** PostgreSQL 16 + TimescaleDB hypertables for compressed telemetry and audit logging.
* **PgBouncer Connection Pooling:** Transaction pooling on port `6432` for high concurrency, paired with direct unpooled access on port `5432` for PostgreSQL `LISTEN/NOTIFY` channels and Alembic migrations.
* **Native Podman Pods & Quadlets:** Production orchestration via declarative systemd Quadlets with tap-less Pasta loopback networking (`platform.pod`).

---

## Visual Tour

<p align="center">
  <img src="docs/assets/login-preview.png" alt="Login Interface" width="48%"/>
  <img src="docs/assets/scalar-preview.png" alt="Scalar OpenAPI Documentation" width="48%"/>
</p>

<p align="center">
  <img src="docs/assets/users-table-preview.png" alt="User Management Table" width="48%"/>
  <img src="docs/assets/swagger-preview.png" alt="Swagger UI Documentation" width="48%"/>
</p>

---

## Quickstart

### 1. Template Generation via Copier

Generate a new application repository using [Copier](https://copier.readthedocs.io/):

```bash
# Install Copier CLI tool
pipx install copier

# Scaffold new project from repository
copier copy git@github.com:le-patrice/granite-template my-project --trust

# Navigate into project directory
cd my-project
```

### 2. Configure Environment

```bash
# Initialize local environment file
cp .env.example .env
```

Review `.env` to configure initial superuser credentials, database passwords, and custom host port overrides.

### 3. Build & Boot Container Stack

```bash
# Build local container images (Backend and Go Telemetry Microservice)
make build

# Launch services in the background (Native Podman Pod)
make up

# Apply database migrations and seed platform superuser
make migrate
make seed
```

---

## Service Endpoints & Interfaces

| Service | Local Address | Authentication / Access |
| :--- | :--- | :--- |
| **Frontend Dashboard** | [http://localhost:8000](http://localhost:8000) | `FIRST_SUPERUSER_EMAIL` / `FIRST_SUPERUSER_PASSWORD` |
| **Backend REST API** | [http://localhost:8000/api/v1](http://localhost:8000/api/v1) | JWT Bearer Token |
| **Go Telemetry Ingest** | `http://localhost:8000/api/v1/telemetry/ingest` | Direct Traefik Microsecond Bypass |
| **Scalar API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Public |
| **Swagger UI Docs** | [http://localhost:8000/docs/swagger](http://localhost:8000/docs/swagger) | Public |
| **Redoc API Docs** | [http://localhost:8000/docs/redoc](http://localhost:8000/docs/redoc) | Public |
| **Health Probes** | [http://localhost:8000/health/ready](http://localhost:8000/health/ready) | Public |
| **Prometheus Metrics** | [http://localhost:8000/metrics](http://localhost:8000/metrics) | Scraper Endpoint |
| **Mailpit Test Inbox** | [http://localhost:8025](http://localhost:8025) | Local Mail Inspector (SMTP :1025) |
| **Traefik Dashboard** | [http://localhost:8080](http://localhost:8080) | Local Development Only |

---

## Command Reference

| Command | Description |
| :--- | :--- |
| `make up` | Start core services in a native Podman Pod (Pasta network + localhost IPC). |
| `make down` | Stop containers cleanly while preserving persistent data volumes. |
| `make build` | Build backend container and compiled Go telemetry microservice. |
| `make migrate` | Apply pending Alembic migrations directly to PostgreSQL port 5432. |
| `make seed` | Provision initial platform superuser from `.env` credentials. |
| `make outbox-listen` | Run dedicated PostgreSQL `LISTEN/NOTIFY` event relay daemon. |
| `make quadlet-dryrun` | Validate production systemd Quadlet unit generation via `podman-system-generator`. |
| `make frontend-sync` | Export OpenAPI 3.1 schema and compile typed Hey-API TypeScript SDK. |
| `make frontend-build` | Validate TypeScript compilation and generate production Vite bundle. |
| `make test` | Run complete Pytest test suite with isolated transactional savepoints. |
| `make lint` | Run Ruff linter and code formatting rules inside container. |
| `make logs` | Stream live aggregated logs across all stack containers. |
| `make logs-api` | Stream unbuffered logs from the Litestar / Granian backend API. |
| `make logs-telemetry` | Stream live logs from the Go telemetry ingest microservice. |

---

## Documentation Index

The complete documentation suite follows the GitBook specification and is located under [`docs/`](docs/):

* **[Summary & Navigation Index](docs/SUMMARY.md)**: Full table of contents for GitBook.
* **[Domain Blueprint](docs/DOMAIN_BLUEPRINT.md)**: Authoritative 12-layer clean architecture standard for scaffolding business domains.
* **[Architecture Specification](docs/ARCHITECTURE.md)**: C4 Level 2 container diagram, native Podman Pod topology, and clean architecture boundaries.
* **[Developer Handbook](docs/DEVELOPMENT.md)**: Environment setup, step-by-step feature tutorial, and automated testing runbook.
* **[Production Deployment](docs/DEPLOYMENT.md)**: Declarative systemd Quadlets, database collision prevention, and Cloudflare Zero Trust tunnel.
* **[Security & RBAC](docs/SECURITY_AND_RBAC.md)**: Argon2id password hashing, JWT lifecycle, and superuser guard gates.
* **[Workers & Resilience](docs/WORKERS_AND_RESILIENCE.md)**: SAQ task queue, real-time Outbox relay, idempotency, and circuit breakers.
* **[Operational Runbook](docs/RUNBOOK.md)**: Automated backup, restore verification, and incident remediation recipes.
