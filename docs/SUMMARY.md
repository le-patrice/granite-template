# Summary

[Overview](../README.md)

## Getting Started
* [Architecture Overview](ARCHITECTURE.md)
* [Developer Handbook](DEVELOPMENT.md)
* [Production Deployment](DEPLOYMENT.md)

## Core Platform
* [Domain Blueprint & Implementation Guide](DOMAIN_BLUEPRINT.md)
* [Security & Access Control (RBAC)](SECURITY_AND_RBAC.md)
* [Distributed Workers & Resilience](WORKERS_AND_RESILIENCE.md)

## Operations & Reliability
* [Operational Runbook & Disaster Recovery](RUNBOOK.md)

## Architecture Decision Records
* [ADR 0001: Litestar & Granian](decisions/0001-use-litestar-and-granian.md)
* [ADR 0002: Rootless Podman & Quadlets](decisions/0002-rootless-podman-and-quadlets.md)
* [ADR 0003: msgspec Serialization](decisions/0003-msgspec-zero-copy-serialization.md)
* [ADR 0004: TimescaleDB & pgvector](decisions/0004-timescaledb-and-pgvector-topology.md)
* [ADR 0005: SAQ & Valkey Task Queue](decisions/0005-saq-and-valkey-for-background-tasks.md)
* [ADR 0006: PgBouncer Connection Pooling](decisions/0006-pgbouncer-connection-pooling.md)
