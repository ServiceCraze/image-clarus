"""Regression checks for schema dependencies, including deferred imports."""

import ast
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "image_clarus"


def test_schema_dependency_graph_includes_deferred_imports_and_is_acyclic():
    modules = {
        "config": PACKAGE / "config.py",
        "schema_worker": PACKAGE / "schema_worker.py",
        "schema_validation": PACKAGE / "schema_validation.py",
        "schema_feedback": PACKAGE / "schema_feedback.py",
        "stages.structure": PACKAGE / "stages" / "structure.py",
    }
    graph = {name: set() for name in modules}
    for name, path in modules.items():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "image_clarus":
                    targets = [alias.name for alias in node.names]
                elif node.module.startswith("image_clarus."):
                    targets = [node.module.removeprefix("image_clarus.")]
                else:
                    targets = []
                graph[name].update(target for target in targets if target in modules)
            elif isinstance(node, ast.Import):
                graph[name].update(
                    alias.name.removeprefix("image_clarus.")
                    for alias in node.names
                    if alias.name.startswith("image_clarus.")
                    and alias.name.removeprefix("image_clarus.") in modules
                )

    def visit(name, active, done):
        assert name not in active, f"dependency cycle: {active + [name]}"
        if name not in done:
            for target in graph[name]:
                visit(target, active + [name], done)
            done.add(name)

    for module in graph:
        visit(module, [], set())
    assert graph["schema_worker"] >= {"schema_validation", "schema_feedback"}
    assert "config" not in graph["schema_worker"]
    assert "stages.structure" not in graph["schema_worker"]


def test_fresh_import_orders_and_compatibility_exports():
    code = """
import importlib
import sys
for name in sys.argv[1:]:
    importlib.import_module("image_clarus." + name)
from image_clarus import config, schema_validation, schema_feedback
from image_clarus.stages import structure
assert config._check_schema is schema_validation._check_schema
assert config._strict_json is schema_validation._strict_json
assert structure._feedback is schema_feedback._feedback
"""
    names = [
        "config",
        "schema_worker",
        "stages.structure",
        "schema_validation",
        "schema_feedback",
    ]
    for order in (names, list(reversed(names))):
        result = subprocess.run(
            [sys.executable, "-c", code, *order],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr
