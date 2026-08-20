# Enterprise Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Litestar](https://img.shields.io/badge/framework-Litestar-yellow.svg)](https://litestar.dev)
[![Granian](https://img.shields.io/badge/server-Granian%20(Rust)-orange.svg)](https://github.com/emmett-framework/granian)
[![Podman](https://img.shields.io/badge/container-Rootless%20Podman-purple.svg)](https://podman.io)
[![PostgreSQL](https://img.shields.io/badge/database-TimescaleDB%20%2B%20pgvector-blue.svg)](https://www.timescale.com/)
[![Valkey](https://img.shields.io/badge/cache-Valkey%208-red.svg)](https://valkey.io/)
[![TypeScript](https://img.shields.io/badge/client-TypeScript-blue.svg)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

High-throughput, asynchronous backend platform engineered with clean domain-driven architecture, zero-copy serialization, and multi-tenant telemetry ingestion capabilities. Built for mission-critical country-scale workloads using [Litestar](https://litestar.dev), [Granian](https://github.com/emmett-framework/granian), [TimescaleDB](https://www.timescale.com/), and [Valkey](https://valkey.io/).

---

## Key Capabilities

- **Zero-Copy High-Throughput Serialization:** Utilizes `msgspec.Struct(frozen=True, gc=False)` across high-velocity telemetry pipelines to bypass garbage collection overhead and achieve native memory parsing speeds.
- **Sub-Millisecond Hot-Path Caching:** Integrated Valkey 8 key-value engine with native Litestar store drivers for sub-millisecond transformer state retrieval and atomic JWT token revocation tracking.
- **Clean Inward-Dependency Architecture:** Strict separation between pure framework-agnostic business logic ([`domain/`](file:///home/pat/Business/LiteStar/backend/src/app/domain/)), persistence and cache adapters ([`adapters/`](file:///home/pat/Business/LiteStar/backend/src/app/adapters/)), and presentation controllers ([`presentation/`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/)).
- **Unified Multi-Modal Database Topology:** Single PostgreSQL 16 engine powering relational platform data, TimescaleDB time-series hypertables for telemetry, `pg_trgm` GIN indexes for fuzzy search, and `pgvector` for machine learning embeddings.
- **Automated Client Synchronization:** End-to-end type safety syncing backend models to frontend clients via `@hey-api/openapi-ts` without manual API binding maintenance.
- **Rootless Production Quadlets:** Declarative Systemd container units ([`deployments/prod/quadlets/`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/)) with automated OCI registry updates, zero-daemon overhead, and non-root SELinux sandbox isolation.

---

## 3-Minute Quickstart (Podman Default)

All developer workflows and database lifecycles run hermetically inside rootless containers.

```bash
# 1. Spin up Postgres, Valkey, and Traefik API mesh
make up

# 2. Apply database migrations (extensions, users, telemetry tables)
make migrate

# 3. Seed default platform superuser (admin@platform.internal)
make seed

# 4. Run the isolated transactional test suite
make test
```

### Access Points

- **API Entrypoint:** [http://localhost/api](http://localhost/api)
- **Interactive Documentation (Scalar):** [http://localhost/docs/scalar](http://localhost/docs/scalar)
- **Interactive Documentation (Swagger):** [http://localhost/docs/swagger](http://localhost/docs/swagger)
- **Traefik Reverse Proxy Dashboard:** [http://localhost:8080](http://localhost:8080)

---

## Documentation Index

The platform documentation follows the [Diátaxis](https://diataxis.fr/) framework:

| Document | Purpose & Framework Quadrant |
| :--- | :--- |
| [**Architecture & Design Blueprint**](file:///home/pat/Business/LiteStar/docs/ARCHITECTURE.md) | **Explanation & Reference** — Arc42 / C4 Level 2 Container architectures, layer boundaries, and database topologies. |
| [**Developer & Contributor Guide**](file:///home/pat/Business/LiteStar/docs/DEVELOPMENT.md) | **Tutorials & How-To Guides** — Step-by-step guides for adding domains, running migrations, client generation, and testing. |
| [**Production Deployment & Operations**](file:///home/pat/Business/LiteStar/docs/DEPLOYMENT.md) | **How-To & Reference** — Systemd Quadlets, rootless container security, Traefik edge ingress, and automated upgrades. |
| [**Operational Runbook & Disaster Recovery**](file:///home/pat/Business/LiteStar/docs/RUNBOOK.md) | **How-To Guides & Reference** — Database backup/restore procedures, connection pool tuning, and incident resolution. |
| [**Architecture Decision Records (ADRs)**](file:///home/pat/Business/LiteStar/docs/decisions/) | **Explanation** — Detailed historical rationale behind architectural and infrastructural choices. |

---

## Architecture Decision Records

- [ADR 0001: Use Litestar and Granian](file:///home/pat/Business/LiteStar/docs/decisions/0001-use-litestar-and-granian.md)
- [ADR 0002: Rootless Podman and Systemd Quadlets](file:///home/pat/Business/LiteStar/docs/decisions/0002-rootless-podman-and-quadlets.md)
- [ADR 0003: Zero-Copy Serialization via msgspec](file:///home/pat/Business/LiteStar/docs/decisions/0003-msgspec-zero-copy-serialization.md)
- [ADR 0004: Unified TimescaleDB and pgvector Database Topology](file:///home/pat/Business/LiteStar/docs/decisions/0004-timescaledb-and-pgvector-topology.md)
