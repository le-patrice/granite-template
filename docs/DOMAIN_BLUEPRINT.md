# Domain Blueprint — Canonical Developer Reference

> **Scope:** This document is the authoritative standard for scaffolding new business domains in Granite, porting external sub-projects into the platform, configuring ORM models, background tasks, and integrating both React/Vite and Astro TypeScript frontends with end-to-end type safety.

---

## Table of Contents

1. [Canonical Domain Directory Structure](#1-canonical-domain-directory-structure)
2. [Layer-by-Layer Implementation Blueprint](#2-layer-by-layer-implementation-blueprint)
3. [Asynchronous Execution Matrix](#3-asynchronous-execution-matrix)
4. [Database Migrations & Alembic Workflow](#4-database-migrations--alembic-workflow)
5. [Full-Stack Frontend Integration](#5-full-stack-frontend-integration)
6. [Step-by-Step Migration Recipe: Porting Standalone Sub-Projects](#6-step-by-step-migration-recipe-porting-standalone-sub-projects)
7. [Rules & Architectural Invariants](#7-rules--architectural-invariants)

---

## 1. Canonical Domain Directory Structure

Every new feature domain follows this layout exactly. Replace `<feature>` with the domain name (e.g., `orders`, `invoicing`, `nlp_pipelines`, `device_telemetry`):

```text
backend/
├── src/app/
│   ├── domain/
│   │   └── <feature>/
│   │       ├── __init__.py         # re-exports: models, schemas, interfaces, services
│   │       ├── models.py           # Pure SQLAlchemy ORM entity (maps to DB table)
│   │       ├── schemas.py          # msgspec.Struct: CreatePayload, UpdatePayload, ReadResponse, FilterParams
│   │       ├── interfaces.py       # Abstract Repository & Service Protocols (typing.Protocol)
│   │       └── services.py         # Pure domain business logic & orchestrators
│   │
│   ├── adapters/
│   │   └── postgres/
│   │       ├── <feature>_repository.py   # Concrete async repository (implements domain protocol)
│   │       └── __init__.py               # imports all models so Alembic auto-detects them
│   │
│   └── presentation/
│       └── api/
│           └── v1/
│               └── <feature>_controller.py  # Litestar Class-Based Controller with DI & Guards
│
├── alembic/
│   └── versions/
│       └── <NNNN>_add_<feature>_tables.py  # Auto-generated Alembic migration
│
└── tests/
    ├── api/
    │   └── test_<feature>.py               # Integration tests (async_client fixture)
    └── domain/
        └── test_<feature>_services.py      # Pure unit tests (no DB)
```

**Rules:**
- The `domain/` layer must **never** import from `adapters/` or `presentation/`. Direction of dependency is always **inward**.
- `adapters/` may import from `domain/` (to implement interfaces) but never from `presentation/`.
- `presentation/` imports from `domain/` (schemas, interfaces) and may use `adapters/` via dependency injection only.

---

## 2. Layer-by-Layer Implementation Blueprint

The canonical example domain is **`orders`**. Adapt naming to your specific domain.

---

### 2.1 Schemas — Data Transfer & Zero-Copy Validation

**File:** `backend/src/app/domain/orders/schemas.py`

Use `msgspec.Struct` with `frozen=True` for sub-millisecond JSON serialization (up to 10× faster than Pydantic v1). All API boundary data must be expressed as Structs.

```python
"""
Order domain schemas.

All API I/O is expressed as msgspec.Struct with frozen=True for immutability
and zero-copy JSON serialization at the Litestar boundary.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import msgspec


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


# ─── Inbound payloads ────────────────────────────────────────────────────────

class OrderCreate(msgspec.Struct, frozen=True):
    """Payload for creating a new order."""

    customer_id: uuid.UUID
    line_items: list[LineItemCreate]
    notes: str | None = None


class LineItemCreate(msgspec.Struct, frozen=True):
    product_sku: str
    quantity: int
    unit_price_cents: int


class OrderUpdate(msgspec.Struct, frozen=True):
    """Partial update — all fields optional."""

    status: OrderStatus | None = None
    notes: str | None = None


# ─── Outbound responses ──────────────────────────────────────────────────────

class LineItemRead(msgspec.Struct, frozen=True):
    id: uuid.UUID
    product_sku: str
    quantity: int
    unit_price_cents: int


class OrderRead(msgspec.Struct, frozen=True):
    id: uuid.UUID
    customer_id: uuid.UUID
    status: OrderStatus
    notes: str | None
    total_cents: int
    line_items: list[LineItemRead]
    created_at: datetime
    updated_at: datetime


# ─── Query / filter params ───────────────────────────────────────────────────

class OrderFilterParams(msgspec.Struct, frozen=True):
    """Used as query-string parameters on list endpoints."""

    customer_id: uuid.UUID | None = None
    status: OrderStatus | None = None
    limit: int = 50
    offset: int = 0
```

---

### 2.2 Interfaces — Domain Contract (Protocol ABCs)

**File:** `backend/src/app/domain/orders/interfaces.py`

```python
"""
Order domain contracts.

All concrete adapters (Postgres, in-memory for tests) must satisfy this Protocol.
Domain services depend only on this interface — never on SQLAlchemy directly.
"""
from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from app.domain.orders.models import Order
from app.domain.orders.schemas import OrderCreate, OrderFilterParams, OrderUpdate


@runtime_checkable
class IOrderRepository(Protocol):
    async def create(self, payload: OrderCreate) -> Order: ...
    async def get_by_id(self, order_id: uuid.UUID) -> Order | None: ...
    async def list(self, filters: OrderFilterParams) -> list[Order]: ...
    async def update(self, order_id: uuid.UUID, payload: OrderUpdate) -> Order | None: ...
    async def delete(self, order_id: uuid.UUID) -> bool: ...
```

---

### 2.3 PostgreSQL ORM Table

**File:** `backend/src/app/domain/orders/models.py`

```python
"""
Order ORM model.

• Inherits AuditBase (UUID PK, created_at, updated_at with server defaults).
• Eager-loads line_items via selectin loading to avoid N+1.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import AuditBase

if TYPE_CHECKING:
    from app.domain.orders.models import LineItem


class Order(AuditBase):
    __tablename__ = "orders"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    line_items: Mapped[list[LineItem]] = relationship(
        "LineItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_orders_customer_status", "customer_id", "status"),
    )


class LineItem(AuditBase):
    __tablename__ = "order_line_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_sku: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="line_items")
```

#### Optional: pgvector Embeddings

For semantic search domains (NLP pipelines, product catalog):

```python
from pgvector.sqlalchemy import Vector

class ProductEmbedding(AuditBase):
    __tablename__ = "product_embeddings"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # 1536 dims = OpenAI text-embedding-3-small / text-embedding-ada-002
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    __table_args__ = (
        # IVFFlat index — tune lists= based on row count (rows / 1000, min 10)
        Index(
            "ix_product_embeddings_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
```

#### Optional: TimescaleDB Hypertable

For high-volume time-series data:

```python
class SensorReading(Base):
    __tablename__ = "sensor_readings"

    # TimescaleDB hypertables partition by time — time column is leading PK.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), primary_key=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    value: Mapped[float] = mapped_column(nullable=False)
```

And in the Alembic migration `upgrade()`:

```python
def upgrade() -> None:
    op.create_table("sensor_readings", ...)

    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM create_hypertable(
                    'sensor_readings', 'recorded_at',
                    chunk_time_interval => INTERVAL '1 day',
                    if_not_exists => true
                );
            END IF;
        END $$;
    """)
```

---

### 2.4 Concrete Async Repository

**File:** `backend/src/app/adapters/postgres/orders_repository.py`

```python
"""
Concrete PostgreSQL implementation of IOrderRepository.

Uses SQLAlchemy 2.0 AsyncSession injected via Litestar's DI.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.orders.models import LineItem, Order
from app.domain.orders.schemas import (
    LineItemRead, OrderCreate, OrderFilterParams, OrderRead, OrderUpdate,
)


class PostgresOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, payload: OrderCreate) -> Order:
        total = sum(li.quantity * li.unit_price_cents for li in payload.line_items)
        order = Order(
            customer_id=payload.customer_id,
            notes=payload.notes,
            total_cents=total,
            line_items=[
                LineItem(
                    product_sku=li.product_sku,
                    quantity=li.quantity,
                    unit_price_cents=li.unit_price_cents,
                )
                for li in payload.line_items
            ],
        )
        self._session.add(order)
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        result = await self._session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def list(self, filters: OrderFilterParams) -> list[Order]:
        query = select(Order)
        if filters.customer_id is not None:
            query = query.where(Order.customer_id == filters.customer_id)
        if filters.status is not None:
            query = query.where(Order.status == filters.status)
        result = await self._session.execute(query.limit(filters.limit).offset(filters.offset))
        return list(result.scalars().all())

    async def update(self, order_id: uuid.UUID, payload: OrderUpdate) -> Order | None:
        order = await self.get_by_id(order_id)
        if order is None:
            return None
        if payload.status is not None:
            order.status = payload.status
        if payload.notes is not None:
            order.notes = payload.notes
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def delete(self, order_id: uuid.UUID) -> bool:
        order = await self.get_by_id(order_id)
        if order is None:
            return False
        await self._session.delete(order)
        await self._session.commit()
        return True


def to_order_read(order: Order) -> OrderRead:
    """Convert ORM entity to API response struct."""
    return OrderRead(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,  # type: ignore[arg-type]
        notes=order.notes,
        total_cents=order.total_cents,
        line_items=[
            LineItemRead(
                id=li.id,
                product_sku=li.product_sku,
                quantity=li.quantity,
                unit_price_cents=li.unit_price_cents,
            )
            for li in order.line_items
        ],
        created_at=order.created_at,
        updated_at=order.updated_at,
    )
```

> **Note:** For simple CRUD with no custom query logic, inherit from `SQLAlchemyAsyncRepository` from `advanced_alchemy` which auto-generates `get`, `list`, `create`, `update`, `delete`.

---

### 2.5 Litestar Class-Based Controller

**File:** `backend/src/app/presentation/api/v1/orders_controller.py`

```python
"""
Orders API Controller.

• Class-level `dependencies` inject the concrete repository via Litestar DI.
• `guards` enforce JWT authentication on all routes in this controller.
• Returns typed msgspec.Struct — Litestar serializes with zero overhead.
"""
from __future__ import annotations

import uuid
from typing import ClassVar

from litestar.controller import Controller
from litestar.di import Provide
from litestar.exceptions import NotFoundException
from litestar.handlers import delete, get, patch, post
from litestar.status_codes import HTTP_204_NO_CONTENT
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.postgres.orders_repository import PostgresOrderRepository, to_order_read
from app.domain.orders.schemas import OrderCreate, OrderFilterParams, OrderRead, OrderUpdate
from app.presentation.guards.auth_guard import require_authenticated


async def provide_orders_repo(db_session: AsyncSession) -> PostgresOrderRepository:
    return PostgresOrderRepository(db_session)


class OrdersController(Controller):
    path = "/orders"
    tags: ClassVar[list[str]] = ["Orders"]
    guards: ClassVar[list] = [require_authenticated]
    dependencies: ClassVar[dict] = {
        "orders_repo": Provide(provide_orders_repo),
    }

    @post("/", status_code=201, summary="Create a new order")
    async def create_order(
        self, data: OrderCreate, orders_repo: PostgresOrderRepository
    ) -> OrderRead:
        order = await orders_repo.create(data)
        return to_order_read(order)

    @get("/", summary="List orders with optional filters")
    async def list_orders(
        self,
        orders_repo: PostgresOrderRepository,
        customer_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRead]:
        filters = OrderFilterParams(
            customer_id=customer_id,
            status=status,  # type: ignore[arg-type]
            limit=limit,
            offset=offset,
        )
        return [to_order_read(o) for o in await orders_repo.list(filters)]

    @get("/{order_id:uuid}", summary="Get an order by ID")
    async def get_order(
        self, order_id: uuid.UUID, orders_repo: PostgresOrderRepository
    ) -> OrderRead:
        order = await orders_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException(f"Order {order_id} not found")
        return to_order_read(order)

    @patch("/{order_id:uuid}", summary="Update an order")
    async def update_order(
        self, order_id: uuid.UUID, data: OrderUpdate, orders_repo: PostgresOrderRepository
    ) -> OrderRead:
        order = await orders_repo.update(order_id, data)
        if order is None:
            raise NotFoundException(f"Order {order_id} not found")
        return to_order_read(order)

    @delete("/{order_id:uuid}", status_code=HTTP_204_NO_CONTENT, summary="Delete an order")
    async def delete_order(
        self, order_id: uuid.UUID, orders_repo: PostgresOrderRepository
    ) -> None:
        if not await orders_repo.delete(order_id):
            raise NotFoundException(f"Order {order_id} not found")
```

---

### 2.6 Registering the Domain

**Register the controller** in `backend/src/app/presentation/api/router.py`:

```python
from app.presentation.api.v1.orders_controller import OrdersController

api_router = Router(
    path="/api/v1",
    route_handlers=[
        # ... existing controllers ...
        OrdersController,
    ],
)
```

**Register the ORM model** in `backend/src/app/adapters/postgres/__init__.py`:

```python
import app.domain.orders.models   # noqa: F401 — registers Order, LineItem on Base.metadata
import app.domain.users.models    # noqa: F401
import app.domain.telemetry.models  # noqa: F401
```

---

## 3. Asynchronous Execution Matrix

Choose the right async tool based on task criticality, duration, and failure-recovery requirements:

| Task Type | Tool | File Placement | Code Pattern |
| :--- | :--- | :--- | :--- |
| **Ephemeral, fire-and-forget** *(transactional emails, webhooks, audit log writes, Slack notifications)* | **Litestar `BackgroundTask`** | Inside the controller handler | `return Response(data, background=BackgroundTask(fn, **kw))` |
| **Long-running, retriable, or scheduled** *(data ingestion pipelines, batch exports, PDF/report generation, LLM inference jobs)* | **SAQ Distributed Worker** | `backend/src/app/core/worker.py` | `await queue.enqueue("task_name", **kw)` |
| **Mission-critical state synchronisation** *(payment events, billing writes, tax submissions, compliance audit trails)* | **Transactional Outbox Pattern** | `backend/src/app/domain/events/` | Save to `outbox_events` inside the **same DB transaction** as the business mutation |

### Pattern A — Litestar BackgroundTask

```python
from litestar import post, Response
from litestar.background_tasks import BackgroundTask

async def send_order_confirmation(order_id: uuid.UUID, email: str) -> None:
    await mailer.send(to=email, template="order_confirmed", context={"order_id": order_id})

@post("/orders")
async def create_order(data: OrderCreate, ...) -> Response[OrderRead]:
    order = await repo.create(data)
    return Response(
        content=to_order_read(order),
        status_code=201,
        background=BackgroundTask(send_order_confirmation, order.id, data.customer_email),
    )
```

### Pattern B — SAQ Worker Task

```python
# backend/src/app/core/worker.py — register the task function
WORKER_TASKS = {
    "generate_order_report": generate_order_report,
}

# In the controller — fire-and-forget, non-blocking
async def trigger_report(order_id: uuid.UUID) -> dict:
    await queue.enqueue("generate_order_report", order_id=str(order_id))
    return {"status": "queued"}
```

### Pattern C — Transactional Outbox

```python
async def create_with_event(self, payload: OrderCreate) -> Order:
    async with self._session.begin():
        order = Order(...)
        self._session.add(order)

        # Atomic — both committed or both rolled back
        event = OutboxEvent(
            event_type="order.created",
            payload_json=msgspec.json.encode({"order_id": str(order.id)}).decode(),
        )
        self._session.add(event)
    return order
```

---

## 4. Database Migrations & Alembic Workflow

### Step 1 — Register the Model

Add to `backend/src/app/adapters/postgres/__init__.py`:

```python
import app.domain.orders.models  # noqa: F401
```

### Step 2 — Generate the Migration

```bash
make migration-create MSG="add_orders_tables"
# or directly:
uv run alembic revision --autogenerate -m "add_orders_tables"
```

### Step 3 — Review the Generated File

Always review `backend/alembic/versions/<NNNN>_add_orders_tables.py`. Verify:

- Correct `down_revision` chain (never `None` unless it's the first migration)
- `CREATE EXTENSION` calls use `IF NOT EXISTS`
- TimescaleDB operations are wrapped in `DO $$ BEGIN IF EXISTS (timescaledb) ... END $$` guard
- `downgrade()` is a complete inverse of `upgrade()` — never left as `pass`

### Step 4 — Apply

```bash
make migrate
# or: uv run alembic upgrade head

# Roll back one revision:
uv run alembic downgrade -1

# Show current state:
uv run alembic current
uv run alembic history --verbose
```

---

## 5. Full-Stack Frontend Integration

The platform provides end-to-end TypeScript type safety:

```
Litestar backend → OpenAPI 3.1 JSON → @hey-api/openapi-ts → TypeScript SDK → React / Astro
```

```bash
make frontend-sync  # runs: export schema → generate client → commit diff
```

The generated `frontend/src/client/` contains:
- `sdk.gen.ts` — typed functions for every API endpoint
- `types.gen.ts` — TypeScript interfaces for all request/response bodies
- `client.ts` — pre-configured fetch client

---

### 5.1 React + Vite + TypeScript (SPA / Dashboard)

**Location:** `frontend/`

```bash
cd frontend && npm ci && npm run generate-client && npm run dev
```

#### Configure the API Client

```typescript
// frontend/src/lib/api.ts
import { client } from "@/client";

client.setConfig({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  headers: {
    get Authorization() {
      const token = localStorage.getItem("access_token");
      return token ? `Bearer ${token}` : undefined;
    },
  },
});
```

#### Query with TanStack React Query

```typescript
// frontend/src/hooks/useOrders.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getOrders, createOrder } from "@/client/sdk.gen";
import type { OrderCreate, OrderRead } from "@/client/types.gen";

export function useOrders(customerId?: string) {
  return useQuery({
    queryKey: ["orders", customerId],
    queryFn: () =>
      getOrders({ query: { customer_id: customerId, limit: 50 } }).then(
        (r) => r.data ?? []
      ),
  });
}

export function useCreateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrderCreate) =>
      createOrder({ body: payload }).then((r) => r.data as OrderRead),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["orders"] }),
  });
}
```

#### Direct SDK Usage (without React Query)

```typescript
import { client } from "@/client";
import { getOrders, createOrder } from "@/client/sdk.gen";

client.setConfig({ baseUrl: "/api/v1" });

// Type-safe — OrderRead[] inferred from OpenAPI schema
const { data, error } = await getOrders({ query: { status: "pending" } });

const { data: newOrder } = await createOrder({
  body: {
    customer_id: "uuid-here",
    line_items: [{ product_sku: "SKU-001", quantity: 2, unit_price_cents: 1999 }],
  },
});
```

---

### 5.2 Astro + TypeScript (Content / SSR / Micro-frontends)

**Location:** `frontend-astro/`

```bash
npm create astro@latest frontend-astro -- --template minimal
cd frontend-astro
npx astro add node        # SSR adapter
npm install @hey-api/client-fetch
```

```javascript
// frontend-astro/astro.config.mjs
import { defineConfig } from "astro/config";
import node from "@astrojs/node";
import react from "@astrojs/react";  // optional — for React islands

export default defineConfig({
  output: "server",
  adapter: node({ mode: "standalone" }),
  integrations: [react()],
  vite: {
    server: { proxy: { "/api": "http://localhost:8000" } },
  },
});
```

#### Share the Generated SDK

```bash
# Symlink (monorepo):
ln -s ../frontend/src/client frontend-astro/src/client

# Or regenerate directly:
cp ../frontend/openapi.json ./openapi.json
npx @hey-api/openapi-ts --input openapi.json --output src/client --client @hey-api/client-fetch
```

#### Server-Side Data Fetching in Astro Pages

```astro
---
// frontend-astro/src/pages/orders/index.astro
import { getOrders } from "@/client/sdk.gen";
import { client } from "@/client";

client.setConfig({
  baseUrl: import.meta.env.INTERNAL_API_URL ?? "http://localhost:8000/api/v1",
  headers: {
    Authorization: `Bearer ${Astro.cookies.get("access_token")?.value ?? ""}`,
  },
});

const { data: orders, error } = await getOrders({ query: { limit: 20 } });
if (error) return Astro.redirect("/login");
---

<html lang="en">
  <body>
    <h1>Orders</h1>
    <ul>
      {orders?.map((order) => (
        <li>{order.id} — {order.total_cents} cents ({order.status})</li>
      ))}
    </ul>
  </body>
</html>
```

#### Astro API Routes (BFF Pattern)

```typescript
// frontend-astro/src/pages/api/orders/index.ts
import type { APIRoute } from "astro";
import { createOrder } from "@/client/sdk.gen";

export const POST: APIRoute = async ({ request, cookies }) => {
  const token = cookies.get("access_token")?.value;
  if (!token) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
  }

  const body = await request.json();
  const { data, error } = await createOrder({
    body,
    headers: { Authorization: `Bearer ${token}` },
  });

  if (error) return new Response(JSON.stringify(error), { status: 400 });
  return new Response(JSON.stringify(data), { status: 201 });
};
```

---

## 6. Step-by-Step Migration Recipe: Porting Standalone Sub-Projects

Use this checklist when absorbing any existing script, microservice, or standalone repository (e.g., ML classifier, FinTech analyser, tax integration) into Granite.

### Phase 1 — Analysis (Do Not Write Code Yet)

- [ ] **Map data structures** — List all existing models, dataclasses, Pydantic schemas, raw dicts.
- [ ] **Identify persistence** — Enumerate all DB tables, file I/O, or external API calls.
- [ ] **Catalogue side effects** — Note all emails, webhooks, queue messages, external writes.
- [ ] **Find entry points** — Locate CLI commands, HTTP handlers, or scheduled jobs.

### Phase 2 — Domain Layer

```bash
mkdir -p backend/src/app/domain/<name>
touch backend/src/app/domain/<name>/{__init__,models,schemas,interfaces,services}.py
```

- [ ] **Translate schemas** — Convert Pydantic models → `msgspec.Struct` with `frozen=True`. Use `X | None` (not `Optional[X]`).
- [ ] **Define the interface** — Write `I<Name>Repository(Protocol)` with only signatures your services need.
- [ ] **Port business logic** — Move rules and transformations into `services.py`. Services receive dependencies via constructor injection.
- [ ] **Define the ORM model** — Write SQLAlchemy 2.0 model inheriting `AuditBase`.

### Phase 3 — Adapter Layer

```bash
touch backend/src/app/adapters/postgres/<name>_repository.py
```

- [ ] **Convert raw SQL** — Replace `cursor.execute()` with SQLAlchemy 2.0 async patterns.
- [ ] **Map legacy ORM** — Rewrite SQLAlchemy 1.x or Django ORM using `mapped_column`/`Mapped[T]`.
- [ ] **Register model** — Add `import app.domain.<name>.models  # noqa: F401` to `adapters/postgres/__init__.py`.

### Phase 4 — Migration

```bash
make migration-create MSG="add_<name>_tables"
# Review the generated file, then:
make migrate
```

### Phase 5 — Presentation Layer

```bash
touch backend/src/app/presentation/api/v1/<name>_controller.py
```

- [ ] **Create the controller** — Wire up `@get`/`@post`/`@patch`/`@delete` routes.
- [ ] **Add guards** — Apply `require_authenticated` (and `require_superadmin` where needed) at class level.
- [ ] **Register** — Add `<Name>Controller` to the router in `presentation/api/router.py`.

### Phase 6 — Background Tasks

- [ ] **Fire-and-forget** (emails, webhooks) → `BackgroundTask` inside the controller.
- [ ] **Long-running** (ingestion, LLM inference) → Enqueue to SAQ in `worker.py`.
- [ ] **Critical state changes** (billing, payments) → Outbox events in the same DB transaction.

### Phase 7 — Tests

```bash
touch backend/tests/api/test_<name>.py
touch backend/tests/domain/test_<name>_services.py
```

- [ ] **Unit tests** — Test `services.py` with a stub/mock repository (no DB needed).
- [ ] **Integration tests** — Use the `async_client` fixture for controller endpoint testing.

### Phase 8 — Frontend Sync

```bash
make frontend-sync
```

- [ ] Verify new endpoint types appear in `frontend/src/client/types.gen.ts`.
- [ ] Commit the updated `frontend/src/client/` directory.
- [ ] Build or update React/Astro pages consuming the new typed SDK functions.

---

## 7. Rules & Architectural Invariants

These rules are enforced by code review and CI — violations block merge:

| # | Rule | Rationale |
| :- | :--- | :--- |
| **1** | Domain layer never imports from `adapters/` or `presentation/` | Dependency inversion — domain is the stable core |
| **2** | All API I/O uses `msgspec.Struct` with `frozen=True` | Sub-millisecond serialization, immutable DTOs |
| **3** | All async database queries use `AsyncSession` (no sync SQLAlchemy) | Prevents greenlet/event-loop blocking |
| **4** | Every `upgrade()` migration has a complete `downgrade()` inverse | Enables safe rollback in production |
| **5** | `CREATE EXTENSION` in migrations always uses `IF NOT EXISTS` | Idempotent migrations in all environments |
| **6** | TimescaleDB operations are guarded with `IF EXISTS (pg_extension WHERE extname = 'timescaledb')` | Works in standard Postgres test environments |
| **7** | Controller class attributes use `typing.ClassVar` | Required by Litestar; satisfies Ruff `RUF012` |
| **8** | `except Exception` always includes `# noqa: BLE001` or catches specific exception type | Ruff `BLE001` — blind exception catching must be intentional |
| **9** | Background tasks use the correct tool per the [Async Execution Matrix](#3-asynchronous-execution-matrix) | Ensures reliability, retryability, and auditability proportional to business impact |
| **10** | `make frontend-sync` is run and the diff committed after any endpoint change | Prevents schema drift detected by the CI `schema-drift` job |

---

*Generated by Antigravity — last updated: 2026-08-20*
