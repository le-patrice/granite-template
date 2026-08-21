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
    
    # Candidate target locations for maximum flexibility across host and containers
    candidates = [
        BACKEND_DIR.parent / "frontend" / "openapi.json",
        Path.cwd() / "frontend" / "openapi.json",
        Path.cwd() / "openapi.json",
        BACKEND_DIR / "openapi.json",
    ]
    
    exported = False
    for target in candidates:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2)
            print(f"✅ Successfully exported OpenAPI schema to: {target}")
            exported = True
            break
        except (PermissionError, OSError):
            continue
            
    if not exported:
        # Fallback to standard output if all filesystem locations are non-writable
        print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    export_schema()
