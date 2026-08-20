# Developer & Contributor Guide

Welcome to the development guide for the Enterprise Platform. This guide is organized according to the [Diátaxis](https://diataxis.fr/) documentation system.

---

## 1. Prerequisites & Environment Setup

All runtime dependencies (Python runtime, PostgreSQL, TimescaleDB, Valkey, Traefik) run hermetically inside rootless containers. You do not need Python or PostgreSQL installed on your host system.

### Required Host Tools
- **Container Engine:** [Podman](https://podman.io/) (v4.5+) and `podman-compose`
- **Build Tool:** GNU `make`

### Optional Local Tools (for local IDE autocompletion)
- **Python:** 3.11+ with [`uv`](https://github.com/astral-sh/uv)
- **Node.js:** 20+ with `npm`

---

## 2. Quickstart Tutorial

Follow these steps to initialize your local development cluster:

```bash
# 1. Clone repository and start container services
git clone <repo-url> && cd LiteStar
make up

# 2. Run initial database migrations
make migrate

# 3. Seed initial platform superuser (admin@platform.internal / AdminSecurePassword2026!)
make seed

# 4. Verify everything works by running the test suite
make test
```

---

## 3. How-To Guides

### How to Add a New Domain Module

Follow this 5-step clean architecture recipe when creating a new domain (e.g., `devices`):

#### Step 1: Define Domain Models & Schemas
Create `backend/src/app/domain/devices/models.py` and `schemas.py`:

```python
# backend/src/app/domain/devices/models.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.domain.base import AuditBase

class Device(AuditBase):
    __tablename__ = "platform_devices"

    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
```

```python
# backend/src/app/domain/devices/schemas.py
import msgspec

class DeviceCreate(msgspec.Struct, frozen=True):
    serial_number: str
    name: str

class DeviceRead(msgspec.Struct, frozen=True):
    id: str
    serial_number: str
    name: str
```

#### Step 2: Define Domain Abstract Contract
Create `backend/src/app/domain/devices/contracts.py`:

```python
# backend/src/app/domain/devices/contracts.py
from abc import ABC, abstractmethod
import uuid
from app.domain.devices.models import Device

class IDeviceRepository(ABC):
    @abstractmethod
    async def get_by_id(self, device_id: uuid.UUID) -> Device | None:
        ...

    @abstractmethod
    async def create(self, device: Device) -> Device:
        ...
```

#### Step 3: Implement Persistence Adapter
Create `backend/src/app/adapters/postgres/device_repository.py`:

```python
# backend/src/app/adapters/postgres/device_repository.py
import uuid
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from app.domain.devices.contracts import IDeviceRepository
from app.domain.devices.models import Device

class PostgresDeviceRepository(SQLAlchemyAsyncRepository[Device], IDeviceRepository):
    model_type = Device

    async def get_by_id(self, device_id: uuid.UUID) -> Device | None:
        return await self.get_one_or_none(id=device_id)

    async def create(self, device: Device) -> Device:
        return await self.add(device)
```

#### Step 4: Implement Controller & Dependency Injection
Create `backend/src/app/presentation/api/v1/devices_controller.py`:

```python
# backend/src/app/presentation/api/v1/devices_controller.py
from litestar import Controller, get, post
from litestar.di import Provide
from sqlalchemy.ext.asyncio import AsyncSession
from app.adapters.postgres.device_repository import PostgresDeviceRepository
from app.domain.devices.contracts import IDeviceRepository
from app.domain.devices.models import Device
from app.domain.devices.schemas import DeviceCreate, DeviceRead
from app.presentation.guards.auth_guard import JWTAuthGuard

async def provide_device_repo(db_session: AsyncSession) -> IDeviceRepository:
    return PostgresDeviceRepository(session=db_session)

class DevicesController(Controller):
    path = "/api/v1/devices"
    guards = [JWTAuthGuard()]
    dependencies = {"device_repo": Provide(provide_device_repo)}

    @post()
    async def create_device(self, data: DeviceCreate, device_repo: IDeviceRepository) -> DeviceRead:
        entity = Device(serial_number=data.serial_number, name=data.name)
        saved = await device_repo.create(entity)
        return DeviceRead(id=str(saved.id), serial_number=saved.serial_number, name=saved.name)
```

#### Step 5: Register Router & Model in Alembic
1. Add `DevicesController` to `backend/src/app/presentation/api/router.py`.
2. Import `app.domain.devices.models` in [`backend/alembic/env.py`](file:///home/pat/Business/LiteStar/backend/alembic/env.py).
3. Generate migration:
   ```bash
   make migrate-revision MSG="add_devices_table"
   make migrate
   ```

---

### How to Manage Database Migrations

All migrations run inside the container to guarantee environment parity:

```bash
# Generate a new migration based on ORM changes
make migrate-revision MSG="add_gin_trgm_index"

# Apply pending migrations
make migrate

# Rollback the last migration
make migrate-down

# View migration history
make migrate-history

# Check currently applied revision in DB
make migrate-show
```

---

### How to Sync Frontend API Clients

The frontend client is generated from the OpenAPI schema using `@hey-api/openapi-ts`:

```bash
# 1. Export OpenAPI spec from Litestar app to dist/openapi.json
make export-schema

# 2. Build the TypeScript client inside the frontend workspace
cd frontend && npm run generate-client
```

CI will automatically fail if the generated client drifts from backend schema changes.

---

### How to Write Fast Transactional Tests

Tests use the `db_session` fixture from [`backend/tests/conftest.py`](file:///home/pat/Business/LiteStar/backend/tests/conftest.py), which wraps test queries inside a `session.begin_nested()` SAVEPOINT. All mutations automatically roll back upon test completion without wiping database schemas.

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_user_and_rollback(async_client: AsyncClient, db_session):
    # This user creation is isolated within a sub-transaction
    response = await async_client.post(
        "/api/v1/users/register",
        json={"email": "isolated@test.internal", "password": "SecurePassword123!", "full_name": "Test User"},
    )
    assert response.status_code == 201

    # When the test function finishes, teardown rolls back the savepoint.
    # Subsequent tests will see a completely clean database.
```

---

## 4. Makefile Command Reference

| Command | Action |
| :--- | :--- |
| `make up` | Start all Podman containers (`postgres`, `valkey`, `app`, `traefik`, `frontend`) |
| `make down` | Tear down containers and wipe local ephemeral networks |
| `make build` | Compile the multi-stage Containerfile |
| `make migrate` | Run `alembic upgrade head` inside the running app container |
| `make migrate-revision MSG="..."` | Generate an autogenerated Alembic migration |
| `make seed` | Execute the idempotent superuser seed script |
| `make test` | Run fast unit and integration tests (`pytest -m "not slow"`) |
| `make test-slow` | Run full migration-cycle test suite against temporary schema |
| `make export-schema` | Export OpenAPI JSON spec to `dist/openapi.json` |
| `make backup` | Execute automated PostgreSQL dump and Valkey snapshot |
| `make restore BACKUP_FILE=...` | Restore database state from a `.dump` archive |
| `make lint` | Run `ruff` check/format on Python and `tsc` on TypeScript |
| `make shell` | Open an interactive bash session inside the backend container |
