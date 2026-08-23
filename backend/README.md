# Litestar Project - Backend

The backend is built with [Litestar](https://litestar.dev/), [Granian](https://github.com/emmett-framework/granian) (Rust ASGI server), [Advanced Alchemy](https://docs.advanced-alchemy.litestar.dev/) / [SQLAlchemy 2.0](https://www.sqlalchemy.org), [Pydantic v2](https://docs.pydantic.dev), [TimescaleDB](https://www.timescale.com), [pgvector](https://github.com/pgvector/pgvector), [Valkey](https://valkey.io), and [SAQ](https://github.com/tobymao/saq) background workers.

## Requirements

* [Podman](https://podman.io/) or [Docker](https://www.docker.com/).
* Python 3.11+ (managed containerized or locally via `uv` / `venv`).

## Local Development with Podman / Docker

Run the entire backend stack containerized with live code reloading via Granian:

```console
$ make up
```

The API is immediately available at `http://localhost:8000`, with automatic interactive OpenAPI documentation at:
- **Swagger UI:** `http://localhost:8000/docs/swagger`
- **Scalar UI:** `http://localhost:8000/docs/scalar`
- **OpenAPI 3.1 Schema:** `http://localhost:8000/docs/openapi.json`

## Granian ASGI Server Configuration

The backend is served by **Granian**, an ultra-high performance HTTP server written in Rust:

* **Development:** Starts with `--reload` mounted on `/app/src` for instant hot-reloading upon file changes.
* **Production:** Configured for multiple Rust workers, cleartext HTTP/2 (`h2c`), and optimal async event loop threading:
  ```bash
  granian --interface asgi app:app --host 0.0.0.0 --port 8000 --workers 4 --http 1 --opt
  ```

## General Workflow

The backend follows Clean Architecture principles:

* **Domain Entities & Models:** Defined in `backend/src/app/domain/<domain>/models.py` using Advanced Alchemy / SQLAlchemy 2.0 Declarative Mapped classes.
* **DTO Schemas:** Defined in `backend/src/app/domain/<domain>/schemas.py` using Pydantic v2 / msgspec Structs.
* **Repository Contracts & Adapters:** Interface contracts in `backend/src/app/domain/<domain>/contracts.py` and Postgres implementations in `backend/src/app/adapters/postgres/`.
* **Controllers & Routing:** Litestar controllers in `backend/src/app/presentation/api/v1/` registered in `backend/src/app/presentation/api/router.py`.

## Database Migrations (Alembic)

Database schema migrations are managed via Alembic against PostgreSQL / TimescaleDB:

* **Apply pending migrations:**
  ```console
  $ make migrate
  ```

* **Generate a new autodetected migration revision:**
  ```console
  $ make migration-create MSG="add_orders_table"
  ```

* **Rollback one migration revision (-1):**
  ```console
  $ make migrate-down
  ```

* **Inspect migration history:**
  ```console
  $ make migrate-history
  ```

* **Direct database shell (`psql`):**
  ```console
  $ make db-shell
  ```

## Backend Tests

The backend test suite runs inside the container using isolated transactional database sessions to prevent test pollution:

```console
$ make test
```

To run a specific test file or test pattern:
```console
$ make test TEST="tests/api/test_auth_and_users.py -k test_login"
```

To run Ruff linter and code formatting validation:
```console
$ make lint
```

## OpenAPI Schema Export & Frontend Client Sync

Whenever API route handlers, parameters, or schema models change, synchronize the typed client SDK for the frontend:

```console
# Export backend OpenAPI schema to frontend/openapi.json and compile TypeScript client SDK
$ make frontend-sync

# Verify zero drift between backend schema and client SDK
$ make check-client-drift
```

## Background Task Processing (SAQ) & Transactional Outbox

* **Start SAQ worker process:**
  ```console
  $ make worker
  ```

* **Tail live worker logs:**
  ```console
  $ make worker-logs
  ```

* **Sweep pending Transactional Outbox events:**
  ```console
  $ make outbox-relay
  ```

* **Replay Dead Letter Queue (DLQ) events:**
  ```console
  $ make dlq-replay
  ```
