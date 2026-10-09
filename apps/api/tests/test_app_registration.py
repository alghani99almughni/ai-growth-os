"""Regression guards for FastAPI app construction and WebCall route registration."""
import ast
from pathlib import Path


def test_main_constructs_fastapi_app_only_once():
    source = Path(__file__).parents[1].joinpath("app", "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    constructions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    assert len(constructions) == 1, "main.py must keep one FastAPI instance so route registrations are not discarded"


def test_webcall_runtime_route_is_registered():
    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/ws/public/webcall/{call_id}" in paths
    assert "/health" in paths
