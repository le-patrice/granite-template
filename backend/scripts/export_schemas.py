"""Export OpenAPI schema definition to JSON."""

import json
import sys
from pathlib import Path

# Ensure backend/src is resolved dynamically in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
SRC_DIR = BACKEND_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import Litestar app instance
from app.main import app  # noqa: E402


def export_schema() -> None:
    schema = app.openapi_schema.to_schema()

    # Potential target file locations
    target_paths = [
        Path("/home/pat/Business/LiteStar/frontend/openapi.json"),
        Path.cwd() / "frontend" / "openapi.json",
        BACKEND_DIR.parent / "frontend" / "openapi.json",
    ]

    for target in target_paths:
        try:
            if target.parent.exists():
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(schema, f, indent=2)
                return
        except (PermissionError, OSError):
            continue

    # Default output as JSON to stdout
    print(json.dumps(schema, indent=2))


if __name__ == "__main__":
    export_schema()
