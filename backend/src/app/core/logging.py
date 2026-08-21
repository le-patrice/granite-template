import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import structlog
from litestar.enums import ScopeType
from litestar.middleware.base import AbstractMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import settings


def setup_logging() -> None:
    log_dir = "logs"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "application.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        handlers.append(file_handler)
    except OSError:
        pass

    # Root standard logger configuration
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
        force=True,
    )

    # Structlog processing pipeline
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.ENVIRONMENT == "production":
        processors = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger("litestar")


class RequestLoggingMiddleware(AbstractMiddleware):
    """ASGI Middleware to log every incoming HTTP request/response cycle in real time."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = logging.getLogger("litestar")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != ScopeType.HTTP:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
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
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            self.logger.info(
                f"{method} {path} HTTP/{scope.get('http_version', '1.1')} {status_code} ({duration_ms}ms)"
            )
