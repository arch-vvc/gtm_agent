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


def test_results_section_is_a_placeholder_or_a_generated_table():
    results = section("Results")
    assert README.count("<!-- results:start -->") == 1
    assert README.count("<!-- results:end -->") == 1
    assert README.index("<!-- results:start -->") < README.index("<!-- results:end -->")
    assert results.index("<!-- results:start -->") < results.index("<!-- results:end -->")
    block = results.split("<!-- results:start -->")[1].split("<!-- results:end -->")[0]
    table_rows = [line for line in block.splitlines() if line.startswith("|")]
    if "PLACEHOLDER" in block:
        assert "results/real_results.csv" in results
        assert len(table_rows[2:]) == 1  # skip the header and the separator
        assert table_rows[2].startswith("| PLACEHOLDER |")
    else:
        assert table_rows[0].startswith("| Company |")
        assert len(table_rows) >= 3


def test_results_refresh_command_is_documented():
    assert "scripts.results_table --write-readme" in section("Results")
    assert "--check" in section("Results")
    assert "scripts.results_table --write-readme" in section("Reproduce the results")


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


def test_status_records_the_live_runs_honestly():
    status = section("Status")
    assert "json_validate_failed" in status
    assert "NOT yet re-run live" in status
    assert "Simular" in status
    assert "no run against live" not in status



def test_status_records_the_latest_live_run_and_the_unverified_fixes():
    status = section("Status")
    assert "Peakflo (cluster B) and Cekura (cluster A) were enriched" in status
    assert "Simular failed" in status
    assert "503" in status
    assert "without trying the second Groq model" in status
    assert "I adapted the simulation engine" in status
    assert "invented a deadline" in status
    assert "NOT yet re-run live" in status
    assert "falls through to the next model" in status
    assert "earlier run on older code" in status
    assert "No results CSV" not in status
