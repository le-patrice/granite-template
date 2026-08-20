# Developer Handbook & Implementation Guide

> **Target Audience:** Backend, Frontend, and Full-Stack Platform Engineers  
> **Standard:** Diátaxis Tutorial & How-To Guide

---

## 1. Local Environment Prerequisites

Ensure the following tools are installed on your workstation:
- **Operating System:** Linux (Ubuntu 22.04+, Fedora 38+, Debian 12+, Arch Linux) or macOS with Podman Machine.
- **Container Engine:** **Podman 4.5+ or 5.x** (configured for rootless operation) or Docker 24+.
- **Compose Provider:** `podman-compose` or `docker-compose-plugin`.
- **Build & Task Automation:** GNU `make` 4.x.
- **Python Tooling:** Python 3.11+ and `uv` (optional for local editor LSP indexers).
- **Frontend Tooling:** Node.js 22+ and `npm` 10+.

---

## 2. Fast Local Bootstrapping

```bash
# 1. Clone your project repository
git clone <repository-url> && cd <project-directory>

# 2. Initialize environment file from template (if not already present)
cp .env.example .env

# 3. Start the full 8-container development stack
make up

# 4. Apply database migrations
make migrate

# 5. Seed default platform superuser
make seed

# 6. Run the complete automated test suite
make test
```

Access your running development services:
- **Application Ingress:** `http://localhost:8000`
- **Interactive Swagger Docs:** `http://localhost:8000/docs/swagger`
- **Interactive Scalar Docs:** `http://localhost:8000/docs/scalar`
- **Traefik Gateway Dashboard:** `http://localhost:8080/dashboard/`
- **Mailpit Email UI:** `http://localhost:8025`
- **Prometheus Metrics:** `http://localhost:8000/metrics`

---

## 3. Tutorial: Adding a New Domain Feature

Follow this step-by-step pattern to introduce a new business capability (e.g. `organizations`) with full clean architecture compliance.

### Step 1: Define Domain Models, Schemas & Contracts
Create `backend/src/app/domain/organizations/`:
- `models.py`: SQLAlchemy declarative entity inheriting from `Base`.
- `schemas.py`: `msgspec.Struct` definitions for input DTOs and responses.
- `contracts.py`: Abstract Protocol interface for the repository.

```python
# backend/src/app/domain/organizations/models.py
import uuid
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.domain.base import Base

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
```

```python
# backend/src/app/domain/organizations/schemas.py
import uuid
import msgspec

class OrganizationCreate(msgspec.Struct, frozen=True):
    name: str

class OrganizationRead(msgspec.Struct, frozen=True):
    id: uuid.UUID
    name: str
```

```python
# backend/src/app/domain/organizations/contracts.py
from abc import ABC, abstractmethod
import uuid
from app.domain.organizations.models import Organization

class IOrganizationRepository(ABC):
    @abstractmethod
    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None: ...
    @abstractmethod
    async def create(self, org: Organization) -> Organization: ...
```

### Step 2: Implement the Postgres Repository Adapter
Create `backend/src/app/adapters/postgres/organization_repository.py`:

```python
import uuid
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from app.domain.organizations.contracts import IOrganizationRepository
from app.domain.organizations.models import Organization

class PostgresOrganizationRepository(SQLAlchemyAsyncRepository[Organization], IOrganizationRepository):
    model_type = Organization

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        return await self.get_one_or_none(id=org_id)

    async def create(self, org: Organization) -> Organization:
        return await self.add(org, auto_commit=True)
```

### Step 3: Build the Presentation Controller
Create `backend/src/app/presentation/api/v1/organizations_controller.py`:

```python
from litestar import Controller, get, post
from litestar.di import Provide
from sqlalchemy.ext.asyncio import AsyncSession
from app.adapters.postgres.organization_repository import PostgresOrganizationRepository
from app.domain.organizations.contracts import IOrganizationRepository
from app.domain.organizations.models import Organization
from app.domain.organizations.schemas import OrganizationCreate, OrganizationRead
from app.presentation.guards.auth_guard import JWTAuthGuard

async def provide_org_repo(db_session: AsyncSession) -> IOrganizationRepository:
    return PostgresOrganizationRepository(session=db_session)

class OrganizationsController(Controller):
    path = "/organizations"
    guards = [JWTAuthGuard()]
    dependencies = {"org_repo": Provide(provide_org_repo)}

    @post(path="/", status_code=201)
    async def create_org(self, data: OrganizationCreate, org_repo: IOrganizationRepository) -> OrganizationRead:
        org = await org_repo.create(Organization(name=data.name))
        return OrganizationRead(id=org.id, name=org.name)
```

### Step 4: Register the Controller
In `backend/src/app/presentation/api/router.py`, include the new controller in `api_router`:

```python
from app.presentation.api.v1.organizations_controller import OrganizationsController

api_router = Router(
    path="/api/v1",
    route_handlers=[
        AuthController,
        UsersController,
        TelemetryController,
        OrganizationsController,
    ],
)
```

### Step 5: Generate and Apply Database Migrations
```bash
# 1. Create autodetected migration revision
make migration-create MSG="add_organizations_table"

# 2. Apply migration into containerized database
make migrate
```

### Step 6: Write Automated Tests
Create `backend/tests/api/test_organizations.py`:

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_organization(async_client: AsyncClient, registered_user: dict):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}
    resp = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Acme Corporation"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corporation"
```

### Step 7: Auto-Sync Frontend TypeScript SDK
```bash
# Exports OpenAPI 3.1 JSON schema and compiles typed TypeScript bindings
make frontend-sync
```

Frontend components can now import strongly-typed client functions directly:
```typescript
import { createOrg } from "@/client";

const response = await createOrg({ body: { name: "Acme Corporation" } });
```
