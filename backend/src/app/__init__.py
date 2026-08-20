from litestar import Litestar, get
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin, SwaggerRenderPlugin
from litestar.status_codes import HTTP_200_OK

from app.adapters.cache.valkey_service import valkey_store
from app.core.database import alchemy_plugin
from app.core.logging import setup_logging
from app.core.settings import settings
from app.presentation.api.router import api_router

# Initialize structured logging engine
setup_logging()


# ---------------------------------------------------------------------------
# Health probe — used by Traefik healthcheck and container orchestrators.
# Intentionally minimal: no DB ping, no auth, always fast.
# ---------------------------------------------------------------------------
@get("/health", status_code=HTTP_200_OK, tags=["ops"], summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok"}


openapi_config = OpenAPIConfig(
    title="Enterprise Core API",
    version="1.0.0",
    path="/docs",
    render_plugins=[
        ScalarRenderPlugin(path="/scalar"),
        SwaggerRenderPlugin(path="/swagger"),
    ],
) if settings.ENVIRONMENT != "production" else None

app = Litestar(
    route_handlers=[api_router, health],
    plugins=[alchemy_plugin],
    stores={"valkey": valkey_store},
    openapi_config=openapi_config,
    debug=settings.DEBUG,
)
