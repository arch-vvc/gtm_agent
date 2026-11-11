"""Checks on README.md that need no network: the promised strings, the cluster table and the commands."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
EN_DASH = chr(0x2013)
EM_DASH = chr(0x2014)


def section(title):
    """Return the text under a '## title' heading, up to the next '## ' heading."""
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", README, re.DOTALL | re.MULTILINE)
    assert match, f"README has no '## {title}' section"
    return match.group(1)


def test_pitch_endpoint_is_documented():
    assert "GET /companies/{company_id}/pitch" in README


def test_no_en_or_em_dash():
    assert EN_DASH not in README
    assert EM_DASH not in README


def test_results_section_is_a_marked_placeholder():
    results = section("Results")
    assert "PLACEHOLDER" in results
    assert "results/real_results.csv" in results
    table_rows = [line for line in results.splitlines() if line.startswith("|")]
    data_rows = table_rows[2:]  # skip the header and the separator
    assert len(data_rows) == 1
    assert data_rows[0].startswith("| PLACEHOLDER |")


def test_cluster_table_lists_a_to_g_and_g_has_no_demo():
    rows = {}
    for line in section("Clusters and demos").splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if line.startswith("|") and len(cells[0]) == 1 and cells[0].isalpha() and cells[0].isupper():
            rows[cells[0]] = cells[-1]
    assert list(rows) == list("ABCDEFG")
    assert "none built" in rows["G"]


def test_no_stale_cluster_ranges():
    assert "A to F" not in README
    assert "C to F" not in README


def test_scripts_named_in_the_readme_exist():
    modules = set(re.findall(r"\bscripts\.([a-z_]+)", README))
    assert "real_run" in modules
    for module in modules:
        assert (ROOT / "scripts" / f"{module}.py").is_file(), f"scripts/{module}.py is named in the README but missing"


def test_compose_services_in_commands_exist():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services = set(re.findall(r"docker compose run --rm (?:-v \"[^\"]*\" )?(\w+)", README))
    assert "worker" in services
    for service in services:
        assert re.search(rf"^  {service}:$", compose, re.MULTILINE), f"{service} is not a service in docker-compose.yml"


def test_csv_flag_is_documented():
    assert "--csv" in README
