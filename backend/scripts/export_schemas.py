"""Export OpenAPI schema definition to JSON."""
from pathlib import Path
import sys
import json

# Ensure backend/src is resolved dynamically in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
SRC_DIR = BACKEND_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import Litestar app instance
from app.main import app

def export_schema() -> None:
    schema = app.openapi_schema.to_schema()
    
    # Target frontend/openapi.json
    output_path = BACKEND_DIR.parent / "frontend" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    
    # Also write to dist/openapi.json for compatibility
    dist_path = BACKEND_DIR.parent / "dist" / "openapi.json"
    dist_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dist_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    
    print(f"✅ Successfully exported OpenAPI schema to: {output_path}")

if __name__ == "__main__":
    export_schema()
