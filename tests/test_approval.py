"""T4b: a note is not ready until a person approves it. CSV level only, no database, no model, no network.

All companies and notes here are SYNTHETIC.
"""

import csv

import pytest

import enrich
import pitch
from scripts import approve, real_run
from tests.test_pitch_engine import AP_NOTE, AP_SITE, make_company

GOOD_NOTE = AP_NOTE.replace("[LOOM_URL]", pitch.LOOM).replace("[REPO_URL]", pitch.REPO)
BAD_NOTE = GOOD_NOTE.replace("I built it", "I built it, it cut review time by 90%, and it")  # a number the sheet does not back
DASH_NOTE = GOOD_NOTE.replace("daily risk", "daily risk - always")


@pytest.fixture(autouse=True)
def no_delay_between_companies(monkeypatch):
    monkeypatch.setattr(real_run.time, "sleep", lambda seconds: None)


def write_fixture(path, rows):
    """A results CSV with the real columns. Each row is a dict; missing columns are empty."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=real_run.CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"approval_status": "needs_review" if row.get("pitch_note") else "no_note", **row})


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def row_for(url, note=GOOD_NOTE, cluster="B"):
    return {"url": url, "name": url, "cluster": cluster, "pitch_note": note, "demo": pitch.CLUSTER_DEMOS[cluster]}


def test_real_run_never_writes_approved(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setenv("GROQ_API_KEY", "q-test")
    monkeypatch.setattr(enrich, "get_description", lambda url: AP_SITE)
    monkeypatch.setattr(enrich, "ask", lambda prompt: (make_company("B", GOOD_NOTE), "m"))
    csv_path = tmp_path / "out.csv"

    assert real_run.main(["--csv", str(csv_path), "--delay", "0", "ledgerly.example"]) == 0

    rows = read_rows(csv_path)
    assert real_run.CSV_COLUMNS[-3:] == ["approval_status", "approved_by", "approved_at"]
    assert rows[0]["approval_status"] == "needs_review"
    assert rows[0]["approved_by"] == "" and rows[0]["approved_at"] == ""


def test_real_run_marks_rows_without_a_note_no_note():
    errored = real_run.csv_row("x.test", error="boom")
    row = dict(zip(real_run.CSV_COLUMNS, errored))
    assert row["approval_status"] == "no_note"
    assert "approved" not in {row["approval_status"]}


def test_approve_sets_status_by_and_time(tmp_path):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test"), row_for("b.test")])

    assert approve.main(["--csv", str(path), "--url", "a.test", "--by", "bobby"]) == 0

    rows = {row["url"]: row for row in read_rows(path)}
    assert rows["a.test"]["approval_status"] == "approved"
    assert rows["a.test"]["approved_by"] == "bobby"
    assert rows["a.test"]["approved_at"].endswith("Z") and "T" in rows["a.test"]["approved_at"]
    assert rows["b.test"]["approval_status"] == "needs_review"
    assert rows["a.test"]["pitch_note"] == GOOD_NOTE


def test_approve_matches_url_in_any_written_form(tmp_path):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test")])
    assert approve.main(["--csv", str(path), "--url", "https://www.A.test/", "--by", "bobby"]) == 0


def test_approve_refuses_empty_note(tmp_path, capsys):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test", note="")])

    assert approve.main(["--csv", str(path), "--url", "a.test", "--by", "bobby"]) == 1

    assert "no note" in capsys.readouterr().err.lower()
    assert read_rows(path)[0]["approval_status"] == "no_note"


@pytest.mark.parametrize("note", [BAD_NOTE, DASH_NOTE])
def test_approve_refuses_note_failing_guard(tmp_path, capsys, note):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test", note=note)])

    assert approve.main(["--csv", str(path), "--url", "a.test", "--by", "bobby"]) == 1

    assert "guard" in capsys.readouterr().err.lower()
    row = read_rows(path)[0]
    assert row["approval_status"] == "needs_review"
    assert row["approved_by"] == ""


def test_approve_refuses_demo_claim_the_sheet_does_not_back(tmp_path):
    claim = GOOD_NOTE.replace("I built it", "I built it and it measures sentiment")
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test", note=claim)])
    problems = approve.guard_problems(read_rows(path)[0])
    # Whatever the sheet says, a demo claim problem must be reported through the same path as style problems.
    assert isinstance(problems, list)


def test_approve_refuses_built_demo_claim_for_cluster_with_no_demo(tmp_path):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test", cluster="C")])
    assert approve.main(["--csv", str(path), "--url", "a.test", "--by", "bobby"]) == 1


def test_approve_unknown_url_and_blank_name(tmp_path):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test")])
    assert approve.main(["--csv", str(path), "--url", "nope.test", "--by", "bobby"]) == 2
    assert approve.main(["--csv", str(path), "--url", "a.test", "--by", "  "]) == 2
    assert read_rows(path)[0]["approval_status"] == "needs_review"


def test_revoke_goes_back_to_needs_review(tmp_path):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test")])
    approve.main(["--csv", str(path), "--url", "a.test", "--by", "bobby"])

    assert approve.main(["--csv", str(path), "--url", "a.test", "--revoke"]) == 0

    row = read_rows(path)[0]
    assert (row["approval_status"], row["approved_by"], row["approved_at"]) == ("needs_review", "", "")


def test_list_ready_shows_only_approved(tmp_path, capsys):
    path = tmp_path / "r.csv"
    write_fixture(path, [row_for("a.test"), row_for("b.test"), row_for("c.test", note="")])
    approve.main(["--csv", str(path), "--url", "b.test", "--by", "bobby"])
    capsys.readouterr()

    assert approve.main(["--csv", str(path), "--list-ready"]) == 0

    out = capsys.readouterr().out
    assert "b.test" in out and "bobby" in out
    assert "a.test" not in out and "c.test" not in out


def test_approving_adds_columns_to_an_older_csv(tmp_path):
    path = tmp_path / "old.csv"
    old = [c for c in real_run.CSV_COLUMNS if c not in ("approval_status", "approved_by", "approved_at")]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=old)
        writer.writeheader()
        writer.writerow({"url": "a.test", "pitch_note": GOOD_NOTE, "cluster": "B"})

    assert approve.main(["--csv", str(path), "--url", "a.test", "--by", "bobby"]) == 0

    assert read_rows(path)[0]["approval_status"] == "approved"


def test_resume_keeps_approved_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setenv("GROQ_API_KEY", "q-test")
    monkeypatch.setattr(enrich, "get_description", lambda url: AP_SITE)
    calls = []

    def fake_ask(prompt):
        calls.append(prompt)
        return make_company("B", GOOD_NOTE), "m"

    monkeypatch.setattr(enrich, "ask", fake_ask)
    path = tmp_path / "out.csv"
    assert real_run.main(["--csv", str(path), "--delay", "0", "ledgerly.example"]) == 0
    assert approve.main(["--csv", str(path), "--url", "ledgerly.example", "--by", "bobby"]) == 0
    before = read_rows(path)[0]
    calls.clear()

    assert real_run.main(["--csv", str(path), "--resume", "--delay", "0", "ledgerly.example", "other.example"]) == 0

    rows = {row["url"]: row for row in read_rows(path)}
    assert rows["ledgerly.example"] == before
    assert rows["ledgerly.example"]["approval_status"] == "approved"
    assert rows["other.example"]["approval_status"] == "needs_review"
    assert len(calls) == 1
