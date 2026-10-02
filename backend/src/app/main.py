"""Application entry point and Litestar ASGI instance."""

try:
    import uvloop

    uvloop.install()
except (ImportError, RuntimeError):
    pass

from app import app

__all__ = ["app"]
