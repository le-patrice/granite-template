"""
OpenAPI 3.1 configuration with OAuth2 Password flow and Bearer JWT security schemes.
"""
from __future__ import annotations

from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin, SwaggerRenderPlugin
from litestar.openapi.spec import Components, OAuthFlow, OAuthFlows, SecurityScheme

from app.core.settings import settings

openapi_config = OpenAPIConfig(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description="Enterprise Platform API with OAuth2 Password flow, Bearer JWT authorization, and RBAC control.",
    path="/docs",
    render_plugins=[
        ScalarRenderPlugin(path="/scalar"),
        SwaggerRenderPlugin(path="/swagger"),
    ],
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
