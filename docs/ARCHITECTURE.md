# System Architecture & Design Blueprint

This document defines the high-level design, component boundaries, and data topologies of the Enterprise Platform, adhering to the [Arc42](https://arc42.org/) structure and [C4 Architectural Model](https://c4model.com/).

---

## 1. C4 Level 2: Container Diagram & Traffic Lifecycle

The platform routes all ingress through a reverse proxy down into an asynchronous application runtime with dual persistence tiers (low-latency cache + multi-modal analytical relational database).

```
                      +------------------------------------------+
                      |         External Client Traffic          |
                      |   (Browsers, IoT Devices, REST SDKs)     |
                      +------------------------------------------+
                                           |
                                           | HTTP/1.1, HTTP/2 (Port 80)
                                           v
+--------------------------------------------------------------------------------------+
| Traefik Edge Reverse Proxy (Port 80)                                                 |
| - Automatic CORS headers & rate-limiting                                             |
| - Route splitting: /api/*, /docs/* -> Backend; /* -> Frontend                        |
+--------------------------------------------------------------------------------------+
         |                                                            |
         | /api/*, /docs/*                                            | /* (Static / HMR)
         v                                                            v
+------------------------------------+                       +-------------------------+
| Litestar Application Runtime       |                       | Frontend Application    |
| (Granian Rust ASGI - Port 8000)    |                       | (Vite Dev / Static OCI) |
| - Controller DI Wiring             |                       +-------------------------+
| - msgspec Zero-Copy Codecs         |
| - JWT & Role-Based Guards          |
+------------------------------------+
         |                                           |
         | Sub-millisecond state & token revocation  | Bulk SQL & Relational queries
         v                                           v
+------------------------------------+   +---------------------------------------------+
| Valkey 8 Cache Store (Port 6379)   |   | PostgreSQL 16 / TimescaleDB (Port 5432)     |
| - transformer:state:<id>           |   | - platform_users (Relational + GIN Trigram) |
| - token:revoked:<jti>              |   | - telemetry_readings (Time-Series Table)    |
| - In-memory Redis compatible engine|   | - pgvector ML Embeddings                    |
+------------------------------------+   +---------------------------------------------+
```

---

## 2. Inward Dependency Boundaries (Clean Architecture)

The codebase strictly enforces clean architecture dependency flow: **Outer layers depend on inner layers; inner layers have zero knowledge of outer layers.**

```
+-------------------------------------------------------------+
| Presentation Layer (Litestar Controllers, Guards, DI)       |  <-- Outer
+-------------------------------------------------------------+
         |
         v
+-------------------------------------------------------------+
| Adapters Layer (PostgreSQL Repositories, Valkey Store)      |
+-------------------------------------------------------------+
         |
         v
+-------------------------------------------------------------+
| Domain Layer (Entities, msgspec Schemas, Abstract Contracts)|  <-- Inner Core
+-------------------------------------------------------------+
```

### A. Domain Layer ([`backend/src/app/domain/`](file:///home/pat/Business/LiteStar/backend/src/app/domain/))
The domain layer represents core business logic and persistence abstractions. It contains zero imports from web frameworks (`litestar`, `fastapi`), HTTP utilities, or database adapters.
- **Contracts ([`contracts.py`](file:///home/pat/Business/LiteStar/backend/src/app/domain/users/contracts.py)):** Strict Python `ABC` abstract classes ([`IUserRepository`](file:///home/pat/Business/LiteStar/backend/src/app/domain/users/contracts.py#L5-L19), [`ITelemetryRepository`](file:///home/pat/Business/LiteStar/backend/src/app/domain/telemetry/contracts.py#L11-L22)).
- **Schemas ([`schemas.py`](file:///home/pat/Business/LiteStar/backend/src/app/domain/telemetry/schemas.py)):** High-throughput data transfer objects defined using `msgspec.Struct(frozen=True, gc=False)` to eliminate garbage collector scanning overhead.
- **Base Models ([`base.py`](file:///home/pat/Business/LiteStar/backend/src/app/domain/base.py)):** Abstract database entities providing automatic UUIDv4 primary keys, UTC audit timestamps (`AuditBase`), and custom dialect-aware vector columns ([`VectorColumn`](file:///home/pat/Business/LiteStar/backend/src/app/domain/base.py#L76-L127)).

### B. Adapters Layer ([`backend/src/app/adapters/`](file:///home/pat/Business/LiteStar/backend/src/app/adapters/))
The adapters layer implements domain contracts using concrete technologies.
- **PostgresUserRepository ([`user_repository.py`](file:///home/pat/Business/LiteStar/backend/src/app/adapters/postgres/user_repository.py)):** Implements `IUserRepository` via Advanced-Alchemy's `SQLAlchemyAsyncRepository[User]`.
- **PostgresTelemetryRepository ([`telemetry_repository.py`](file:///home/pat/Business/LiteStar/backend/src/app/adapters/postgres/telemetry_repository.py)):** Implements `ITelemetryRepository` using raw parameterised SQL `session.execute(stmt, records)` for maximum insertion throughput during bulk IoT ingestion.
- **Valkey Caching Adapter ([`valkey_service.py`](file:///home/pat/Business/LiteStar/backend/src/app/adapters/cache/valkey_service.py)):** Exposes `ValkeyStore` for hot transformer state caching and fast session revocation checks.

### C. Presentation Layer ([`backend/src/app/presentation/`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/))
The presentation layer manages HTTP transport, request validation, authentication, and responses.
- **Dependency Injection:** Controllers declare dependencies via `Provide()`. Repositories and services are injected dynamically per request scope.
- **Controllers ([`api/v1/`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/api/v1/)):** Class-based controllers ([`AuthController`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/api/v1/auth_controller.py), [`UsersController`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/api/v1/users_controller.py), [`TelemetryController`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/api/v1/telemetry_controller.py)).
- **Guards ([`guards/auth_guard.py`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/guards/auth_guard.py)):** [`JWTAuthGuard`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/guards/auth_guard.py#L38-L86) validates JWT headers and interrogates Valkey for `jti` revocation before routing. [`SuperuserGuard`](file:///home/pat/Business/LiteStar/backend/src/app/presentation/guards/auth_guard.py#L88-L113) enforces role-based authorization.

---

## 3. Database & Extension Topology

The database runtime runs PostgreSQL 16 with native C-extensions enabled:

```
+-------------------------------------------------------------------------------+
| PostgreSQL 16 (TimescaleDB-HA) Database Instance                              |
|                                                                               |
|  +-------------------------+  +-------------------------+                     |
|  | uuid-ossp               |  | btree_gin               |                     |
|  | (Native UUID gen)       |  | (Compound index ops)    |                     |
|  +-------------------------+  +-------------------------+                     |
|  +-------------------------+  +-------------------------+                     |
|  | pg_trgm                 |  | vector (pgvector)       |                     |
|  | (GIN fuzzy text search) |  | (L2 / Cosine embeddings)|                     |
|  +-------------------------+  +-------------------------+                     |
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  | Table: platform_users                                                   |  |
|  | - Primary Key: UUID                                                     |  |
|  | - GIN Trigram Index on (email gin_trgm_ops)                             |  |
|  | - GIN Trigram Index on (full_name gin_trgm_ops)                         |  |
|  +-------------------------------------------------------------------------+  |
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  | Table: telemetry_readings (TimescaleDB Hypertable ready)                 |  |
|  | - Dimensions: transformer_id (String), recorded_at (TIMESTAMPTZ)        |  |
|  | - Composite Index on (transformer_id, recorded_at DESC)                 |  |
|  | - Metric Fields: voltage_v, current_a, power_factor, frequency_hz        |  |
|  +-------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------+
```

### Extension Usage Patterns

1. **`uuid-ossp`:** Provides `uuid_generate_v4()` for database-level default primary keys.
2. **`pg_trgm` & `btree_gin`:** Provides trigram indexing (`gin_trgm_ops`) on `platform_users.email` and `platform_users.full_name`, allowing sub-millisecond regex, prefix, and fuzzy matching (`ILIKE '%query%'`) across millions of records without table scans.
3. **`vector`:** Integrates with the custom [`VectorColumn`](file:///home/pat/Business/LiteStar/backend/src/app/domain/base.py#L76-L127) type to store high-dimensional embeddings (e.g. 1536 dimensions for OpenAI or text-embedding-3) and perform vector distance queries (`<->`, `<=>`).
4. **TimescaleDB Engine:** Handles high-volume continuous telemetry ingestion partitioned along `recorded_at` time-windows, enabling automatic chunk compression and retention policies.
