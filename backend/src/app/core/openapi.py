"""OpenAPI 3.1 configuration with OAuth2 Password flow, Bearer JWT, and selectable UI."""

from __future__ import annotations

from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import (
    RapidocRenderPlugin,
    RedocRenderPlugin,
    ScalarRenderPlugin,
    StoplightRenderPlugin,
    SwaggerRenderPlugin,
)
from litestar.openapi.spec import Components, OAuthFlow, OAuthFlows, SecurityScheme

from app.core.settings import settings


def get_render_plugins() -> list:
    """Build OpenAPI render plugins list prioritized by settings.DOCS_UI (default: swagger)."""
    plugins_map = {
        "swagger": SwaggerRenderPlugin(path="/swagger"),
        "scalar": ScalarRenderPlugin(path="/scalar"),
        "redoc": RedocRenderPlugin(path="/redoc"),
        "elements": StoplightRenderPlugin(path="/elements"),
        "rapidoc": RapidocRenderPlugin(path="/rapidoc"),
    }

    selected = settings.DOCS_UI.lower().strip()
    primary = plugins_map.get(selected, plugins_map["swagger"])

    # Place primary selected UI first (which renders on /docs), followed by alternatives
    ordered_plugins = [primary]
    for plugin in plugins_map.values():
        if plugin is not primary:
            ordered_plugins.append(plugin)

    return ordered_plugins


openapi_config = OpenAPIConfig(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description="Enterprise Platform API with OAuth2 Password flow, Bearer JWT authorization, and RBAC control.",
    path="/docs",
    render_plugins=get_render_plugins(),
    components=Components(
        security_schemes={
            "BearerAuth": SecurityScheme(
                type="http",
                scheme="bearer",
                bearer_format="JWT",
                description="Enter JWT Bearer token directly: Bearer <token>",
            ),
            "OAuth2Password": SecurityScheme(
                type="oauth2",
                flows=OAuthFlows(
                    password=OAuthFlow(
                        token_url="/api/v1/auth/login",
                        scopes={},
                    )
                ),
                description="Standard Swagger / Scalar OAuth2 username & password login",
            ),
        }
    ),
    security=[{"BearerAuth": []}, {"OAuth2Password": []}],
)
