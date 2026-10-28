"""Guard the domain boundary independently of HTTP and database behavior."""

import ast
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = PROJECT_ROOT / "app" / "domain"


def test_domain_imports_only_standard_library_and_domain_modules():
    violations = []
    for path in DOMAIN_ROOT.rglob("*.py"):
        package = ".".join(path.parent.relative_to(PROJECT_ROOT).parts)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = "." * node.level + (node.module or "")
                modules = [resolve_name(name, package) if node.level else name]
                # Resolve `from app import ...` before checking the layer boundary.
                if modules == ["app"]:
                    modules = [f"app.{alias.name}" for alias in node.names]
            else:
                continue
            for module in modules:
                if module == "app.domain" or module.startswith("app.domain."):
                    continue
                if module.split(".", 1)[0] not in sys.stdlib_module_names:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}: {module}")
    assert not violations, "Domain imports outside its boundary:\n" + "\n".join(violations)


def test_domain_tests_run_without_site_packages(tmp_path):
    # -I ignores PYTHONPATH/user configuration; -S disables loading site-packages.
    script = """
import sys
import unittest
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_domain.py')
assert suite.countTestCases() > 0
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, str(PROJECT_ROOT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
