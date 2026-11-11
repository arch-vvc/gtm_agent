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
BAD_DASHES = re.compile("[\u2010-\u2015\u2212]")
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


@pytest.mark.parametrize("char", ["\u2011", "\u2013", "\u2014", "\u2212"])
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


INJECTION = "<script>alert(1)</script> [x](http://evil) ![x](http://evil/a.png) `c`"


def unescaped(text):
    """Drop every backslash escaped pair, leaving only characters Markdown would act on."""
    return re.sub(r"\\.", "", text)


def test_markdown_and_html_are_neutralised_in_every_cell():
    row = make_row(
        name=INJECTION, cluster=INJECTION, demo=INJECTION, cluster_reason=INJECTION,
        pitch_note=INJECTION, error=INJECTION, pitch_error=INJECTION,
    )

    for cell in results_table.table_cells(row):
        rest = unescaped(cell)
        for bad in ("<", ">", "](", "![", "`", "[", "("):
            assert bad not in rest
    assert "failed: " in results_table.findings(row)
    assert "note rejected: " in results_table.findings(row)


def test_normal_sentence_with_parentheses_reads_sensibly():
    assert results_table.md_escape("Built it (fast)! See docs.") == "Built it \\(fast\\)\\! See docs."


def test_escape_does_not_double_escape_and_pipes_still_work():
    row = make_row(name="a|b (c)", pitch_note="x")

    line = results_table.markdown_line(results_table.table_cells(row))

    assert line.startswith("| a\\|b \\(c\\) |")
    assert "\\\\" not in line


def test_fixed_text_stays_unescaped():
    block = results_table.build_block([make_row(name="X", error="boom")])

    assert "| Cluster reason (quoted from the site) |" in block
    assert "failed: boom" in block
    assert "_Generated by scripts/results_table.py" in block
    assert "none found by the automatic checks" in results_table.findings(make_row(name="X"))


def test_write_readme_has_no_raw_html_or_links(tmp_path):
    csv_path = write_csv(tmp_path / "r.csv", [make_row(name="Acme", cluster_reason=INJECTION, pitch_note=INJECTION)])
    readme = readme_with(tmp_path)

    assert results_table.main(["--csv", str(csv_path), "--readme", str(readme), "--write-readme"]) == 0

    text = readme.read_text(encoding="utf-8")
    assert "<script" not in text
    assert "](http" not in text
    assert not BAD_DASHES.search(text)


def test_utf8_bom_does_not_break_first_column(tmp_path, capsys):
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbfname,url,pitch_note\nAcme,a.co,hello\n")

    assert results_table.main(["--csv", str(path)]) == 0

    assert "| Acme |" in capsys.readouterr().out


def test_non_utf8_csv_fails_with_one_line(tmp_path, capsys):
    path = tmp_path / "latin.csv"
    path.write_bytes(b"name,pitch_note\nx,caf\xe9")

    assert results_table.main(["--csv", str(path)]) == 1

    err = capsys.readouterr().err
    assert "latin.csv" in err and len(err.strip().splitlines()) == 1


def test_directory_as_csv_fails_clearly(tmp_path, capsys):
    assert results_table.main(["--csv", str(tmp_path)]) == 1

    assert str(tmp_path) in capsys.readouterr().err


def test_unreadable_readme_fails_clearly(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "r.csv", [make_row(name="Acme")])
    bad = tmp_path / "README.md"
    bad.write_bytes(b"\xff\xfe\xfa")

    assert results_table.main(["--csv", str(csv_path), "--readme", str(bad), "--check"]) == 1

    err = capsys.readouterr().err
    assert "README.md" in err and len(err.strip().splitlines()) == 1


def test_missing_columns_fail_clearly(tmp_path, capsys):
    no_note = tmp_path / "a.csv"
    no_note.write_text("name,url\nx,y\n", encoding="utf-8")
    no_id = tmp_path / "b.csv"
    no_id.write_text("pitch_note\nhello\n", encoding="utf-8")

    assert results_table.main(["--csv", str(no_note)]) == 1
    assert "pitch_note" in capsys.readouterr().err
    assert results_table.main(["--csv", str(no_id)]) == 1
    assert "name" in capsys.readouterr().err
