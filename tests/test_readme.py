"""Checks on README.md and docs/DESIGN.md that need no network: the promised strings, the cluster table and the commands."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
DESIGN = (ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
EVAL_DOC = (ROOT / "docs" / "EVAL.md").read_text(encoding="utf-8")
EN_DASH = chr(0x2013)
EM_DASH = chr(0x2014)


def section(title, text=README):
    """Return the text under a '## title' heading, up to the next '## ' heading."""
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    assert match, f"no '## {title}' section"
    return match.group(1)


def test_pitch_endpoint_is_documented():
    assert "GET /companies/{company_id}/pitch" in DESIGN


def test_no_en_or_em_dash():
    for text in (README, DESIGN, EVAL_DOC):
        assert EN_DASH not in text
        assert EM_DASH not in text


def test_cluster_table_lists_a_to_g_and_g_has_no_demo():
    rows = {}
    for line in section("Clusters and demos", DESIGN).splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if line.startswith("|") and len(cells[0]) == 1 and cells[0].isalpha() and cells[0].isupper():
            rows[cells[0]] = cells[-1]
    assert list(rows) == list("ABCDEFG")
    assert "none built" in rows["G"]


def test_no_stale_cluster_ranges():
    for text in (README, DESIGN):
        assert "A to F" not in text
        assert "C to F" not in text


def test_readme_is_short_and_has_no_company_rows():
    lines = README.splitlines()
    assert len(lines) <= 90
    assert "| Peakflo |" not in README
    assert not [line for line in lines if line.startswith("| Company")]
    assert "<!-- results:start -->" not in README
    headings = re.findall(r"^## (.+)$", README, re.MULTILINE)
    assert headings[0] == "Results"
    assert "docs/EVAL.md" in README and "docs/DESIGN.md" in README


def test_readme_scripts_exist():
    modules = set(re.findall(r"\bscripts\.([a-z_]+)", README))
    assert "golden_eval" in modules
    for module in modules:
        assert (ROOT / "scripts" / f"{module}.py").is_file(), f"scripts/{module}.py is named in the README but missing"


def test_design_notes_hold_the_moved_sections():
    titles = (
        "API", "Clusters and demos", "How the grounding guard works", "Careers page",
        "Answer quality and duplicates", "How the Gemini to Groq fallback works", "Database migration",
        "Running it", "Limits", "Status history",
    )  # fmt: skip
    for title in titles:
        assert re.search(rf"^## {re.escape(title)}$", DESIGN, re.MULTILINE), title


def test_design_keeps_the_run_commands_and_the_private_table_note():
    running = section("Running it", DESIGN)
    assert "scripts.real_run" in running and "--csv" in running
    assert "docker compose run --rm" in running
    assert "private/results_table.md" in running
    for module in set(re.findall(r"\bscripts\.([a-z_]+)", running)):
        assert (ROOT / "scripts" / f"{module}.py").is_file(), module
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in set(re.findall(r"docker compose run --rm (?:-v \"[^\"]*\" )*(\w+)", running)):
        assert re.search(rf"^  {service}:$", compose, re.MULTILINE), service


def test_eval_doc_has_the_failure_buckets():
    for bucket in ("A)", "B)", "C)", "D)", "E)"):
        assert bucket in EVAL_DOC
    for name in ("Certa", "DevRev", "CollectWise", "LiveKit"):
        assert name in EVAL_DOC


def test_status_records_the_live_runs_honestly():
    status = section("Status history", DESIGN)
    assert "json_validate_failed" in status
    assert "NOT yet re-run live" in status
    assert "Simular" in status
    assert "no run against live" not in status


def test_status_records_the_latest_live_run_and_the_unverified_fixes():
    status = section("Status history", DESIGN)
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
