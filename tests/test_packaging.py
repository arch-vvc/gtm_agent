"""Packaging checks: the Docker image has every module the app imports."""

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINTS = ["main.py", "worker.py"]


def _local_modules() -> set[str]:
    return {p.stem for p in ROOT.glob("*.py")}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def _needed_modules() -> set[str]:
    """Local modules reachable from the entry points, following imports."""
    local = _local_modules()
    seen: set[str] = set()
    todo = [Path(ROOT / e) for e in ENTRY_POINTS]
    while todo:
        path = todo.pop()
        for name in _imports(path) & local:
            if name not in seen:
                seen.add(name)
                todo.append(ROOT / f"{name}.py")
    return seen | {Path(e).stem for e in ENTRY_POINTS}


def _copied_files() -> set[str]:
    copied: set[str] = set()
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        if line.startswith("COPY ") and "--from" not in line:
            copied.update(line.split()[1:-1])
    return copied


def test_dockerfile_copies_every_imported_local_module():
    copied = _copied_files()
    missing = sorted(m for m in _needed_modules() if f"{m}.py" not in copied)
    assert not missing, f"Dockerfile COPY is missing: {missing}"


def test_dockerfile_copies_scripts_folder():
    assert "scripts" in _copied_files()


def test_pyproject_has_a_real_description():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    description = data["project"]["description"]
    assert "Add your description here" not in description
    assert len(description) > 20


def test_pyproject_has_no_script_entry_for_missing_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "scripts" not in data["project"]
    assert not (ROOT / "src").exists()
    assert not (ROOT / "how_to_run.txt").exists()


def test_pyproject_is_not_packaged():
    text = (ROOT / "pyproject.toml").read_text()
    assert re.search(r"(?m)^package\s*=\s*false", text)
