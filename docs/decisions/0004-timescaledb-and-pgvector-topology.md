# ADR 0004: Unified TimescaleDB and pgvector Database Topology

- **Status:** Accepted
- **Date:** 2026-08-20
- **Deciders:** Principal Database Architect, Data Platform Team

---

## Context

The platform requires a data persistence architecture capable of supporting three distinct storage and query modalities:
1. **ACID Relational Storage:** User accounts, authentication state, permissions, and entity metadata.
2. **High-Frequency Time-Series Data:** High-velocity IoT telemetry readings requiring continuous time-window aggregation, hypertable partitioning, and automatic data chunk compression.
3. **High-Dimensional Vector Embeddings:** Nearest-neighbor similarity search for upcoming machine learning models, anomaly detection, and semantic search.

Deploying separate database engines (e.g. standard PostgreSQL + InfluxDB/Prometheus + Pinecone/Qdrant) introduces significant distributed systems overhead, synchronization lag, backup fragmentation, and multiple points of operational failure.

---

## Decision

We unified all three data modalities into a single **PostgreSQL 16** database instance powered by the **TimescaleDB-HA** distribution with native C-extensions:

```
+-------------------------------------------------------------------------------+
| Single PostgreSQL 16 Instance                                                |
|                                                                               |
|  [Relational Core]          [TimescaleDB Extension]     [pgvector Extension]  |
|  - Users, Auth, Audit       - Hypertables & Chunks      - ML Embeddings       |
|  - ACID Transactions        - Continuous Aggregates     - Cosine / L2 Distance|
|  - Foreign Key Constraints  - Time Partitioning         - Vector Indexing     |
|                                                                               |
|  [pg_trgm & btree_gin Extensions]                                             |
|  - Sub-millisecond fuzzy substring search (ILIKE '%query%')                   |
+-------------------------------------------------------------------------------+
```

### Key Architectural Drivers

1. **Transactional Integrity & Single Pane of Glass:** A single SQL engine allows cross-domain queries joining time-series readings directly to relational user and asset tables in a single ACID transaction.
2. **Unified Backup & Disaster Recovery:** Standard `pg_dump -Fc` captures all relational records, hypertables, and vector indexes in one atomic, consistent backup archive.
3. **Reduced Infrastructure Complexity:** Eliminates cross-database ETL pipelines, operational overhead, and specialized connection drivers.

---

## Consequences

### Positive
- **Operational Simplicity:** Only one database engine to monitor, scale, back up, and secure.
- **Rich SQL Ecosystem:** Full standard SQL access across relational, time-series, and vector search operations.
- **PgBouncer Compatibility:** Standard connection pooling and PgBouncer transaction-mode support out of the box (`statement_cache_size=0`).

### Negative / Trade-offs
- **Single Database Resource Sizing:** Compute and memory must be allocated to accommodate both analytical time-series queries and relational transactions concurrently.
- **Specialized Base Image:** Requires the `timescale/timescaledb-ha:pg16` container image rather than vanilla upstream `postgres:16-alpine`.
