import json
import os
from app import app

def export_openapi() -> None:
    os.makedirs("dist", exist_ok=True)
    schema = app.openapi_schema.to_schema()
    with open("dist/openapi.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print("Exported OpenAPI schema to dist/openapi.json")

if __name__ == "__main__":
    export_openapi()
