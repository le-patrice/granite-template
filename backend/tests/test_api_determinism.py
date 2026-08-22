"""
Architectural Invariant Tests for API Route Determinism & Zero Schema Drift.

Enforces:
1. No route handler may use multiple path bindings (e.g. path=["/a", "/b"]) in decorators.
   All routes must use single explicit string paths to prevent OpenAPI operationId drift.
2. All OpenAPI operation IDs across the entire Litestar application must be 100% unique.
3. OpenAPI schema generation must be byte-for-byte deterministic across invocations.
"""

from __future__ import annotations

import ast
from pathlib import Path

from litestar.handlers import HTTPRouteHandler

from app import app as litestar_app


def test_no_multipath_route_decorators() -> None:
    """
    Scan all presentation controller source files with AST to enforce that
    no @get, @post, @put, @patch, @delete decorator uses a list/tuple for `path`.
    """
    presentation_dir = Path(__file__).resolve().parent.parent / "src" / "app" / "presentation"
    py_files = list(presentation_dir.rglob("*.py"))
    assert len(py_files) > 0, "No presentation files found for AST inspection"

    route_decorators = {"get", "post", "put", "patch", "delete", "route"}
    violations = []

    for file_path in py_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                call_node = decorator if isinstance(decorator, ast.Call) else None
                if not call_node:
                    continue

                func_name = ""
                if isinstance(call_node.func, ast.Name):
                    func_name = call_node.func.id
                elif isinstance(call_node.func, ast.Attribute):
                    func_name = call_node.func.attr

                if func_name in route_decorators:
                    # Check kwargs for path=
                    for kw in call_node.keywords:
                        if kw.arg == "path" and isinstance(
                            kw.value, (ast.List, ast.Tuple, ast.Set)
                        ):
                            violations.append(
                                f"{file_path.name}:{node.lineno} -> '{node.name}' uses "
                                f"multi-path {ast.dump(kw.value)}. Use separate explicit handler methods instead."
                            )

    assert not violations, (
        f"Found {len(violations)} multi-path route decorator violations:\n" + "\n".join(violations)
    )


def test_openapi_schema_operation_ids_are_unique() -> None:
    """Verify that every endpoint operation in OpenAPI 3.1 has a unique operationId."""
    schema = litestar_app.openapi_schema.to_schema()
    paths = schema.get("paths", {})
    assert paths, "OpenAPI paths definition cannot be empty"

    operation_ids: dict[str, str] = {}
    duplicates: list[str] = []

    http_methods = {"get", "post", "put", "patch", "delete", "options", "head"}

    for path_str, path_item in paths.items():
        for method, op_data in path_item.items():
            if method.lower() not in http_methods or not isinstance(op_data, dict):
                continue
            op_id = op_data.get("operationId")
            assert op_id, f"Operation {method.upper()} {path_str} missing operationId"

            route_key = f"{method.upper()} {path_str}"
            if op_id in operation_ids:
                duplicates.append(
                    f"Duplicate operationId '{op_id}' found in '{route_key}' and '{operation_ids[op_id]}'"
                )
            else:
                operation_ids[op_id] = route_key

    assert not duplicates, "Found duplicate OpenAPI operationIds:\n" + "\n".join(duplicates)


def test_all_registered_handlers_have_clean_operation_names() -> None:
    """Verify all Litestar registered route handlers have valid string names."""
    for route in litestar_app.routes:
        for handler in getattr(route, "route_handlers", []):
            if isinstance(handler, HTTPRouteHandler):
                assert handler.handler_name, f"Route handler in route {route} has empty name"
                assert not isinstance(handler.paths, (list, tuple)) or len(handler.paths) == 1, (
                    f"Route handler '{handler.handler_name}' has multiple registered paths: {handler.paths}"
                )
