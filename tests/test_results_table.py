"""Tests for scripts/results_table.py. No network and no API keys."""

import csv
import re
from pathlib import Path

import pytest

from scripts import results_table

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = [
    "url",
    "name",
    "cluster",
    "demo",
    "hiring_fde",
    "cluster_reason",
    "customer_pain",
    "tailoring",
    "pitch_note",
    "pitch_error",
    "model",
    "error",
]
BAD_DASHES = re.compile("[‐-―−]")
NOTE = "I built demo A for voice teams.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]"


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def make_row(**fields):
    row = dict.fromkeys(COLUMNS, "")
    row.update(fields)
    return row


def table_lines(rows, tmp_path):
    block = results_table.build_block(rows)
    return [line for line in block.splitlines() if line.startswith("|")]


def cells_of(rows):
    return [results_table.table_cells(row) for row in rows]


def test_good_failed_and_claim_rows():
    good = make_row(
        url="a.co", name="Acme", cluster="A", demo="voice-agent-call-qa", hiring_fde="true",
        cluster_reason="Voice testing.", pitch_note=NOTE,
    )
    failed = make_row(url="b.co", hiring_fde="false", error="boom")
    claim = make_row(url="c.co", name="Cee", cluster="A", demo="d", pitch_note="I adapted the engine.")

    good_cells, failed_cells, claim_cells = cells_of([good, failed, claim])

    assert good_cells == [
        "Acme", "A", "voice-agent-call-qa", "yes", "Voice testing.",
        "I built demo A for voice teams.", "none found by the automatic checks",
    ]
    assert failed_cells[:4] == ["b.co", "n/a", "n/a", "no"]
    assert failed_cells[6] == "failed: boom"
    assert "'I adapted'" in claim_cells[6]


def test_pitch_error_and_note_checks_are_listed_in_order():
    row = make_row(name="X", pitch_error="too long", pitch_note="I adapted it.")

    found = results_table.findings(row).split("; ")

    assert found[0] == "note rejected: too long"
    assert any("'I adapted'" in item for item in found)


def test_hiring_label_mapping():
    assert results_table.hiring_label("true") == "yes"
    assert results_table.hiring_label("false") == "no"
    assert results_table.hiring_label("") == "unknown"


def test_truncation():
    long_note = "word " * 100
    long_reason = "reason " * 100

    cells = results_table.table_cells(make_row(name="X", cluster_reason=long_reason, pitch_note=long_note))

    assert 200 < len(cells[5]) <= 223 and cells[5].endswith("...")
    assert len(cells[4]) <= 163 and cells[4].endswith("...")
    assert results_table.shorten("short", 10) == "short"


def test_pipes_are_escaped_and_newlines_collapse():
    row = make_row(name="A | B", cluster_reason="line one\r\nline   two", pitch_note="\n\nfirst | line\nsecond")

    line = results_table.markdown_line(results_table.table_cells(row))

    assert "A \\| B" in line
    assert "line one line two" in line
    assert "first \\| line" in line
    assert "second" not in line
    assert "\n" not in line


@pytest.mark.parametrize("char", ["‑", "–", "—", "−"])
def test_dash_like_characters_never_reach_the_output(char):
    row = make_row(name=f"A{char}B", cluster_reason=f"x {char} y", error=f"e{char}f", pitch_note=f"p{char}q")

    block = results_table.build_block([row])

    assert not BAD_DASHES.search(block)
    assert " - " not in block


def test_empty_csv_gives_no_rows_line(tmp_path, capsys):
    path = write_csv(tmp_path / "r.csv", [])

    assert results_table.main(["--csv", str(path)]) == 0

    assert capsys.readouterr().out.strip() == "No rows yet."


def test_missing_csv_fails_clearly(tmp_path, capsys):
    assert results_table.main(["--csv", str(tmp_path / "nope.csv")]) == 1

    assert "not found" in capsys.readouterr().err


def readme_with(tmp_path, body="old"):
    path = tmp_path / "README.md"
    path.write_text(f"before\n{results_table.START_MARKER}\n{body}\n{results_table.END_MARKER}\nafter\n", encoding="utf-8")
    return path


def test_write_readme_replaces_only_the_block_and_is_idempotent(tmp_path):
    csv_path = write_csv(tmp_path / "r.csv", [make_row(name="Acme", cluster="A", pitch_note=NOTE)])
    readme = readme_with(tmp_path)
    args = ["--csv", str(csv_path), "--readme", str(readme), "--write-readme"]

    assert results_table.main(args) == 0
    first = readme.read_text(encoding="utf-8")
    assert results_table.main(args) == 0

    assert readme.read_text(encoding="utf-8") == first
    assert first.startswith("before\n<!-- results:start -->\n| Company |")
    assert first.endswith("<!-- results:end -->\nafter\n")
    assert "old" not in first


def test_missing_or_misordered_markers_fail(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "r.csv", [make_row(name="Acme")])
    missing = tmp_path / "missing.md"
    missing.write_text("no markers\n", encoding="utf-8")
    swapped = tmp_path / "swapped.md"
    swapped.write_text(f"{results_table.END_MARKER}\n{results_table.START_MARKER}\n", encoding="utf-8")

    for readme in (missing, swapped):
        before = readme.read_text(encoding="utf-8")
        assert results_table.main(["--csv", str(csv_path), "--readme", str(readme), "--write-readme"]) == 1
        assert readme.read_text(encoding="utf-8") == before
        assert "error:" in capsys.readouterr().err


def test_check_exit_codes(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "r.csv", [make_row(name="Acme")])
    readme = readme_with(tmp_path)
    args = ["--csv", str(csv_path), "--readme", str(readme)]

    assert results_table.main([*args, "--check"]) == 1
    assert "out of date" in capsys.readouterr().out
    results_table.main([*args, "--write-readme"])
    assert results_table.main([*args, "--check"]) == 0


def test_real_committed_results():
    block = results_table.build_block(results_table.read_rows(ROOT / "results" / "real_results.csv"))

    assert not BAD_DASHES.search(block)
    cekura = next(line for line in block.splitlines() if line.startswith("| Cekura |"))
    assert "'I adapted'" in cekura
