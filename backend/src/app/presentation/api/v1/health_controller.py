"""
Three-Stage Kubernetes / Container Liveness, Readiness, and Startup Health Probes.

Routes:
  • GET /health/live    – Liveness probe: verifies ASGI event loop responsiveness.
  • GET /health/ready   – Readiness probe: verifies DB (PostgreSQL) + Cache (Valkey) availability.
  • GET /health/startup – Startup probe: validates database migration baseline.
  • GET /health         – General health status.
"""

from __future__ import annotations

from typing import Any, ClassVar

from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings


class HealthController(Controller):
    path = "/health"
    opt: ClassVar[dict[str, bool]] = {"exclude_from_auth": True}

    @get(
        path=["", "/"],
        status_code=HTTP_200_OK,
        summary="Basic Health Status",
        description="Returns standard healthy indicator.",
    )
    async def get_health(self) -> dict[str, str]:
        return {"status": "ok"}

    @get(
        path="/live",
        status_code=HTTP_200_OK,
        summary="Liveness Probe",
        description="Kubernetes liveness check: immediate 200 if ASGI event loop is active.",
    )
    async def get_liveness(self) -> dict[str, str]:
        return {"status": "alive"}

    @get(
        path="/ready",
        status_code=HTTP_200_OK,
        summary="Readiness Probe",
        description="Deep dependency health check: verifies PostgreSQL and Valkey connectivity.",
    )
    async def get_readiness(self, db_session: AsyncSession) -> dict[str, Any]:
        results: dict[str, str] = {}
        all_ready = True

        # 1. PostgreSQL check
        try:
            res = await db_session.execute(text("SELECT 1"))
            if res.scalar() == 1:
                results["database"] = "healthy"
            else:
                results["database"] = "unhealthy"
                all_ready = False
        except Exception as exc:  # noqa: BLE001
            results["database"] = f"error: {exc!s}"
            all_ready = False

        # 2. Valkey check
        try:
            import valkey.asyncio as valkey

            v_client = valkey.Valkey(
                host=settings.VALKEY_HOST,
                port=settings.VALKEY_PORT,
                socket_timeout=1.5,
            )
            pong = await v_client.ping()
            await v_client.aclose()
            if pong:
                results["valkey"] = "healthy"
            else:
                results["valkey"] = "unhealthy"
                all_ready = False
        except Exception as exc:  # noqa: BLE001
            # Valkey might be optional in certain test environments
            results["valkey"] = f"error: {exc!s}"
            # Don't fail readiness completely if valkey is mock-only in dev, but flag it
            if settings.ENVIRONMENT == "production":
                all_ready = False

        if not all_ready and results.get("database") != "healthy":
            raise HTTPException(
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "not_ready", "dependencies": results},
            )

        return {"status": "ready", "dependencies": results}

    @get(
        path="/startup",
        status_code=HTTP_200_OK,
        summary="Startup Probe",
        description="Validates that database migrations are executed and operational.",
    )
    async def get_startup(self, db_session: AsyncSession) -> dict[str, Any]:
        try:
            # Check alembic_version table
            res = await db_session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            version = res.scalar_one_or_none()
            return {
                "status": "started",
                "schema_version": version or "initial",
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "startup_failed", "error": str(exc)},
            )
