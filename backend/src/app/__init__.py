from litestar import Litestar
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin, SwaggerRenderPlugin

from app.adapters.cache.valkey_service import valkey_store
from app.core.database import alchemy_plugin
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import setup_logging
from app.core.metrics import PrometheusMetricsMiddleware, metrics_endpoint
from app.core.settings import settings
from app.presentation.api.router import api_router
from app.presentation.api.v1.health_controller import HealthController

# Initialize structured logging engine
setup_logging()

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
    route_handlers=[HealthController, metrics_endpoint, api_router],
    plugins=[alchemy_plugin],
    middleware=[PrometheusMetricsMiddleware, IdempotencyMiddleware],
    stores={"valkey": valkey_store},
    openapi_config=openapi_config,
    debug=settings.DEBUG,
)
