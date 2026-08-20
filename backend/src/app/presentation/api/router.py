from litestar import Router

from app.presentation.api.v1.auth_controller import AuthController
from app.presentation.api.v1.telemetry_controller import TelemetryController
from app.presentation.api.v1.users_controller import UsersController

api_router = Router(
    path="/api/v1",
    route_handlers=[AuthController, UsersController, TelemetryController],
)
