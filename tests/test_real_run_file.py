import csv

import pytest

import enrich
from scripts import real_run
from tests.test_pitch_engine import AP_NOTE, make_company


def good_result(url):
    return {
        "name": url,
        "company": make_company("B", AP_NOTE),
        "demo": "invoice-exception-triage",
        "model": "gemini-3.5-flash",
        "pitch_note": AP_NOTE,
        "pitch_error": None,
        "careers_url": None,
        "hiring_fde": None,
        "error": None,
    }


def failed_result(url):
    out = good_result(url)
    out.update(company=None, demo=None, model=None, pitch_note=None, error="Could not fetch the site")
    return out


@pytest.fixture
def calls(monkeypatch):
    """Fake enrich.enrich: records the URLs it was asked for. Hosts containing 'bad' fail."""
    seen = []

    def fake(url):
        seen.append(url)
        return failed_result(url) if "bad" in url else good_result(url)

    monkeypatch.setattr(enrich, "enrich", fake)
    monkeypatch.setattr(real_run.time, "sleep", lambda seconds: None)
    return seen


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_file_with_comments_blanks_and_a_duplicate(tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("# my list\n\npeakflo.co\n   \n  # indented comment\nhttps://www.Peakflo.co/\ncekura.ai\n")

    assert real_run.read_url_file(str(path)) == ["peakflo.co", "cekura.ai"]


def test_file_and_arguments_are_merged_without_duplicates(calls, tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("peakflo.co\ncekura.ai\n")

    code = real_run.main(["--file", str(path), "--delay", "0", "cekura.ai", "ledgerly.example"])

    assert code == 0
    assert sorted(calls) == ["cekura.ai", "ledgerly.example", "peakflo.co"]


def test_missing_file_exits_2(calls, tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        real_run.main(["--file", str(tmp_path / "nope.txt")])

    assert exit_info.value.code == 2
    assert "nope.txt" in capsys.readouterr().err
    assert calls == []


def test_empty_file_exits_2(calls, tmp_path, capsys):
    path = tmp_path / "targets.txt"
    path.write_text("# only a comment\n\n")

    with pytest.raises(SystemExit) as exit_info:
        real_run.main(["--file", str(path)])

    assert exit_info.value.code == 2
    assert "no URLs" in capsys.readouterr().err
    assert calls == []


def test_no_urls_and_no_file_exits_2(calls):
    with pytest.raises(SystemExit) as exit_info:
        real_run.main([])

    assert exit_info.value.code == 2


def test_resume_skips_the_finished_row_and_retries_the_failed_one(calls, tmp_path):
    out = tmp_path / "results.csv"
    real_run.main(["--csv", str(out), "--delay", "0", "done.example", "bad.example"])
    assert calls == ["done.example", "bad.example"]
    calls.clear()

    code = real_run.main(["--csv", str(out), "--resume", "--delay", "0", "done.example", "bad.example", "new.example"])

    assert calls == ["bad.example", "new.example"]
    rows = read_rows(out)
    assert [row["url"] for row in rows] == ["done.example", "bad.example", "new.example"]
    assert rows[0]["error"] == ""
    assert rows[1]["error"] == "Could not fetch the site"
    assert code == 1  # bad.example failed again
    assert out.read_text().count("url,name,cluster") == 1


def test_resume_without_csv_exits_2(calls, capsys):
    with pytest.raises(SystemExit) as exit_info:
        real_run.main(["--resume", "peakflo.co"])

    assert exit_info.value.code == 2
    assert "--csv" in capsys.readouterr().err
    assert calls == []


def test_resume_with_no_csv_file_yet_runs_everything(calls, tmp_path):
    out = tmp_path / "fresh.csv"

    real_run.main(["--csv", str(out), "--resume", "--delay", "0", "a.example", "b.example"])

    assert calls == ["a.example", "b.example"]
    assert len(read_rows(out)) == 2


def test_resume_when_everything_is_done_makes_no_calls(calls, tmp_path, capsys):
    out = tmp_path / "results.csv"
    real_run.main(["--csv", str(out), "--delay", "0", "a.example"])
    calls.clear()

    code = real_run.main(["--csv", str(out), "--resume", "a.example"])

    assert code == 0
    assert calls == []
    assert len(read_rows(out)) == 1


def test_delay_zero_does_not_sleep(calls, monkeypatch):
    slept = []
    monkeypatch.setattr(real_run.time, "sleep", slept.append)

    real_run.main(["--delay", "0", "a.example", "b.example", "c.example"])

    assert slept == []


def test_default_delay_is_5_seconds_between_companies_but_not_after_the_last(calls, monkeypatch):
    slept = []
    monkeypatch.setattr(real_run.time, "sleep", slept.append)

    real_run.main(["a.example", "b.example", "c.example"])

    assert slept == [5, 5]


def test_progress_line_per_company(calls, capsys):
    real_run.main(["--delay", "0", "a.example", "b.example"])

    out = capsys.readouterr().out
    assert "1 of 2" in out
    assert "2 of 2" in out


def test_help_shows_the_new_options(capsys):
    with pytest.raises(SystemExit):
        real_run.main(["--help"])

    out = capsys.readouterr().out
    for option in ("--file", "--resume", "--delay"):
        assert option in out
