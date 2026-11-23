"""The compose file must be safe to run on a laptop. It is checked as text; Docker is never started."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = (ROOT / "docker-compose.yml").read_text()


def test_every_published_port_is_loopback_only():
    ports = re.findall(r'^\s*-\s*"?(\d[^"\n]*:\d+)"?\s*$', COMPOSE, re.MULTILINE)
    assert ports, "expected at least one published port"
    for port in ports:
        assert port.startswith("127.0.0.1:"), port


def test_db_and_api_ports_are_published_on_loopback():
    assert '"127.0.0.1:5432:5432"' in COMPOSE
    assert '"127.0.0.1:8000:8000"' in COMPOSE


def test_db_password_comes_from_a_variable_with_a_default():
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-secret}" in COMPOSE
    assert "POSTGRES_PASSWORD: secret" not in COMPOSE


def test_readme_says_default_password_is_local_only():
    readme = (ROOT / "docs/DESIGN.md").read_text()
    assert "default database password is for local use only" in readme
