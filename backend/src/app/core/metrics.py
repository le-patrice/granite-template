"""
Prometheus Metrics & Observability Collector.

Exposes standard Prometheus metric formats on `GET /metrics` and includes
an ASGI middleware to record request counts and duration percentiles.
"""

from __future__ import annotations

import time

from litestar import get
from litestar.enums import ScopeType
from litestar.middleware.base import AbstractMiddleware
from litestar.response import Response
from litestar.status_codes import HTTP_200_OK
from litestar.types import ASGIApp, Message, Receive, Scope, Send
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# Metric Definitions
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests processed.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency percentiles in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

DB_POOL_ACTIVE_CONNECTIONS = Gauge(
    "db_connection_pool_active",
    "Number of active database connections checked out.",
)

TELEMETRY_INGEST_RECORDS_TOTAL = Counter(
    "telemetry_ingest_records_total",
    "Total count of telemetry sensor records ingested.",
)


# ---------------------------------------------------------------------------
# Metrics Middleware
# ---------------------------------------------------------------------------


class PrometheusMetricsMiddleware(AbstractMiddleware):
    """ASGI Middleware to capture request count & latency metrics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != ScopeType.HTTP:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Do not record metrics for the metrics endpoint itself
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start_time = time.monotonic()
        status_code = 200

        async def tracking_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        finally:
            duration = time.monotonic() - start_time
            # Normalize path for metric cardinality (avoid UUIDs or IDs leaking into label names)
            route_handler = scope.get("route_handler")
            if route_handler and hasattr(route_handler, "paths") and route_handler.paths:
                normalized_path = next(iter(route_handler.paths))
            elif path.startswith("/health"):
                normalized_path = path
            elif path.startswith("/api"):
                import re

                # Scrub UUIDs and numeric IDs to prevent memory leaks in Prometheus registry
                cleaned = re.sub(
                    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                    "/{id}",
                    path,
                )
                normalized_path = re.sub(r"/\d+", "/{id}", cleaned)
            else:
                normalized_path = "/other"

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=normalized_path,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                path=normalized_path,
            ).observe(duration)


# ---------------------------------------------------------------------------
# Route Handler: GET /metrics
# ---------------------------------------------------------------------------


@get(
    path="/metrics",
    status_code=HTTP_200_OK,
    media_type=CONTENT_TYPE_LATEST,
    opt={"exclude_from_auth": True},
    tags=["ops"],
    summary="Prometheus Metrics",
    description="Prometheus scrapable text exposition metric stream.",
)
async def metrics_endpoint() -> Response[bytes]:
    data = generate_latest(REGISTRY)
    return Response(
        content=data,
        status_code=HTTP_200_OK,
        media_type=CONTENT_TYPE_LATEST,
    )
