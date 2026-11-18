import csv
import hashlib
from pathlib import Path

import openpyxl
import pytest

from scripts import real_run, tracker_sync

# Every company, role and note here is SYNTHETIC.
HEADER = ["#", "Company", "Role", "Location (as listed)", "Setup", "Fresher fit", "Cluster", "Link", "Status"]
ROWS = [
    ["1", "Alpha Voice (YC W22)", "Forward Deployed Engineer", "India, Remote", "India remote", "Good", "A Voice", "https://jobs.lever.co/alpha/abc-123", "To research"],
    ["2", "Alpha Voice (YC W22)", "FDE Intern", "Remote", "India remote", "Good", "A Voice", "Open", "To research"],
    ["3", "Beta Books", "Solutions Engineer", "Bengaluru", "India onsite", "Stretch", "B Finance", "https://www.instahyre.com/job-1/", "To research"],
    ["4", "Gamma Ghost", "FDE", "Remote", "India remote", "Good", "C Enterprise", "Open", "To research"],
    ["5", "Delta Down", "FDE", "Remote", "India remote", "Check", "E Infra", "Open", "To research"],
]
DOMAINS = [("Alpha Voice", "alpha.example"), ("Beta Books", "beta.example"), ("Delta Down", "delta.example")]


def write_tracker(path, rows=ROWS):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def write_domains(path, rows=DOMAINS):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["url", "company", "expected_cluster", "label_source"])
        writer.writerows([[url, company, "A", "test"] for company, url in rows])
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_tracker_reads_a_csv_with_a_bom_and_keeps_a_link_only_if_it_is_a_url(tmp_path):
    rows = tracker_sync.read_tracker(write_tracker(tmp_path / "t.csv"))

    assert [row["Company"] for row in rows] == ["Alpha Voice (YC W22)", "Alpha Voice (YC W22)", "Beta Books", "Gamma Ghost", "Delta Down"]
    assert rows[0]["job_url"] == "https://jobs.lever.co/alpha/abc-123"
    assert rows[1]["job_url"] is None  # "Open" is a label, not a link


def test_read_tracker_reads_the_hyperlink_target_from_an_xlsx_cell(tmp_path):
    path = tmp_path / "t.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "India & Remote"
    sheet.append(HEADER)
    sheet.append(ROWS[0][:7] + ["Open", "To research"])
    sheet["H2"].hyperlink = "https://jobs.lever.co/alpha/abc-123"
    other = workbook.create_sheet("How to use")
    other.append(["not a tracker sheet"])
    workbook.save(path)

    rows = tracker_sync.read_tracker(path)

    assert len(rows) == 1
    assert rows[0]["Company"] == "Alpha Voice (YC W22)"
    assert rows[0]["job_url"] == "https://jobs.lever.co/alpha/abc-123"


def test_company_key_ignores_the_yc_batch_and_case():
    assert tracker_sync.company_key("Alpha Voice (YC W22)") == tracker_sync.company_key("alpha voice")


def test_build_targets_runs_each_company_once_and_gives_every_row_its_url(tmp_path):
    rows = tracker_sync.read_tracker(write_tracker(tmp_path / "t.csv"))
    domains = tracker_sync.read_domains(write_domains(tmp_path / "d.csv"))

    targets, skipped = tracker_sync.build_targets(rows, domains)

    assert targets == {"alpha.example": "https://jobs.lever.co/alpha/abc-123", "beta.example": None, "delta.example": None}
    assert [row["Company"] for row in skipped] == ["Gamma Ghost"]
    assert [row["url"] for row in rows if row.get("url")] == ["alpha.example", "alpha.example", "beta.example", "delta.example"]


def test_a_website_column_in_the_tracker_beats_the_domains_file(tmp_path):
    rows = [{"Company": "Alpha Voice", "Website": "alpha.example/home", "job_url": None}]

    targets, skipped = tracker_sync.build_targets(rows, {"alpha voice": "other.example"})

    assert list(targets) == ["alpha.example/home"]
    assert skipped == []


def test_score_adds_documented_points_and_says_why():
    row = {"demo": "invoice-exception-triage", "pitch_note": "n", "Fresher fit": "Good", "hiring_fde": "True", "cluster": "B", "Cluster": "B Finance"}

    score, reason = tracker_sync.score_row(row)

    assert score == 9
    assert "demo built +3" in reason and "note +2" in reason and "fresher fit +2" in reason
    assert "hiring FDE +1" in reason and "cluster agrees +1" in reason


def test_score_is_low_when_nothing_was_built_or_the_note_failed():
    row = {"demo": "none built", "pitch_note": "", "Fresher fit": "Check", "hiring_fde": "False", "cluster": "C", "Cluster": "E Infra"}

    assert tracker_sync.score_row(row)[0] == 0


RAW = [
    # Alpha: answered, demo built, note, hiring.
    {"url": "alpha.example", "name": "Alpha", "cluster": "A", "demo": "voice-agent-call-qa", "hiring_fde": "True",
     "pitch_note": "I built a demo.", "pitch_error": "", "error": "", "evidence": "q1 | q2"},
    # Beta: answered but the guard rejected the note.
    {"url": "beta.example", "name": "Beta", "cluster": "F", "demo": "none built", "hiring_fde": "",
     "pitch_note": "", "pitch_error": "Pitch note rejected: names not found on the site: X", "error": "", "evidence": ""},
    # Delta: failed.
    {"url": "delta.example", "name": "Delta", "cluster": "", "demo": "", "hiring_fde": "",
     "pitch_note": "", "pitch_error": "", "error": "Could not reach site", "evidence": ""},
]


def fake_engine(raw_rows):
    calls = []

    def run(targets_path, raw_csv, resume, delay):
        calls.append({"targets": Path(targets_path).read_text(encoding="utf-8").split("\n"), "resume": resume, "delay": delay})
        with open(raw_csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=real_run.CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(raw_rows)
        return 0

    return run, calls


def read_out(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_main(tmp_path, monkeypatch, extra=()):
    tracker = write_tracker(tmp_path / "t.csv")
    domains = write_domains(tmp_path / "d.csv")
    engine, calls = fake_engine(RAW)
    monkeypatch.setattr(tracker_sync, "run_engine", engine)
    out = tmp_path / "out" / "ranked.csv"
    code = tracker_sync.main([str(tracker), "--domains", str(domains), "--out", str(out), *extra])
    return code, out, calls, tracker


def test_main_writes_one_ranked_row_per_tracker_row_and_never_touches_the_tracker(tmp_path, monkeypatch):
    before = digest(tmp_path / "t.csv") if (tmp_path / "t.csv").exists() else None
    code, out, calls, tracker = run_main(tmp_path, monkeypatch)
    before = before or digest(tracker)
    rows = read_out(out)

    assert code == 0
    assert digest(tracker) == before
    assert len(rows) == 5
    assert calls[0]["targets"][0] == "alpha.example https://jobs.lever.co/alpha/abc-123"
    assert "gamma" not in " ".join(calls[0]["targets"]).lower()
    ready = [row for row in rows if row["status"] == "ready"]
    assert [row["company"] for row in ready] == ["Alpha Voice (YC W22)", "Alpha Voice (YC W22)"]
    assert [row["rank"] for row in ready] == ["1", "2"]
    statuses = {row["company"]: row["status"] for row in rows}
    assert statuses["Beta Books"] == "no note"
    assert statuses["Delta Down"] == "failed: Could not reach site"
    assert statuses["Gamma Ghost"] == "no website"
    assert rows[0]["evidence"] == "q1 | q2"
    assert rows[0]["cluster_agrees"] == "yes"
    assert [row["status"] for row in rows[-3:]] != ["ready"] * 3


def test_rows_that_are_not_ready_come_last_and_have_no_rank(tmp_path, monkeypatch):
    _, out, _, _ = run_main(tmp_path, monkeypatch)
    rows = read_out(out)

    assert [row["status"] == "ready" for row in rows] == [True, True, False, False, False]
    assert all(row["rank"] == "" for row in rows if row["status"] != "ready")


def test_resume_and_delay_are_passed_to_the_engine(tmp_path, monkeypatch):
    _, _, calls, _ = run_main(tmp_path, monkeypatch, ["--resume", "--delay", "9"])

    assert calls[0]["resume"] is True
    assert calls[0]["delay"] == 9


def test_dry_run_prints_the_plan_and_calls_no_engine(tmp_path, monkeypatch, capsys):
    tracker = write_tracker(tmp_path / "t.csv")
    domains = write_domains(tmp_path / "d.csv")
    monkeypatch.setattr(tracker_sync, "run_engine", lambda *a, **k: pytest.fail("the engine must not run"))

    code = tracker_sync.main([str(tracker), "--domains", str(domains), "--out", str(tmp_path / "o.csv"), "--dry-run"])
    text = capsys.readouterr().out

    assert code == 0
    assert "5 tracker rows" in text and "3 companies to run" in text and "1 with a job link" in text
    assert "no website: Gamma Ghost" in text
    assert not (tmp_path / "o.csv").exists()


def test_the_output_path_may_not_be_the_tracker(tmp_path, monkeypatch, capsys):
    tracker = write_tracker(tmp_path / "t.csv")
    before = digest(tracker)
    monkeypatch.setattr(tracker_sync, "run_engine", lambda *a, **k: pytest.fail("the engine must not run"))

    code = tracker_sync.main([str(tracker), "--out", str(tracker)])

    assert code == 2
    assert "would overwrite the tracker" in capsys.readouterr().out
    assert digest(tracker) == before


def test_a_missing_tracker_exits_2(tmp_path, capsys):
    code = tracker_sync.main([str(tmp_path / "nope.csv"), "--out", str(tmp_path / "o.csv")])

    assert code == 2
    assert "cannot read" in capsys.readouterr().out


def test_the_results_csv_now_carries_the_evidence_quotes():
    assert real_run.CSV_COLUMNS[-1] == "evidence"
    row = dict(zip(real_run.CSV_COLUMNS, real_run.csv_row("a.example", out={
        "name": "A", "demo": "none built", "hiring_fde": None, "pitch_note": "n", "pitch_error": None,
        "model": "m", "error": None, "company": None, "evidence": ["first quote here", "second quote here"],
    })))

    assert row["evidence"] == "first quote here | second quote here"
