import csv
from pathlib import Path

import pytest

from scripts import golden_eval

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_HEADER = ["url", "company", "expected_cluster", "label_source"]
RESULT_HEADER = ["url", "name", "cluster", "cluster_reason", "pitch_note", "pitch_error", "error"]

# Every company here is SYNTHETIC.
GOLDEN = [
    ("alpha.example", "Alpha", "A"),
    ("beta.example", "Beta", "B"),
    ("gamma.example", "Gamma", "C"),
    ("delta.example", "Delta", "E"),
]


def write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def golden_file(tmp_path, rows=GOLDEN):
    return write(tmp_path / "golden.csv", GOLDEN_HEADER, [[u, n, c, "test"] for u, n, c in rows])


def results_file(tmp_path, rows):
    return write(tmp_path / "results.csv", RESULT_HEADER, rows)


# alpha right, beta wrong (got A, expected B), gamma failed, delta never run.
RESULTS = [
    ["alpha.example", "Alpha", "A", "Alpha tests voice agents.", "I built a demo.", "", ""],
    ["beta.example", "Beta", "A", "Beta says it answers calls.", "", "Pitch note rejected: names not found on the site: X", ""],
    ["gamma.example", "Gamma", "", "", "", "", "The model could not fill in industry (answered 'UNKNOWN') from the site text."],
]


def test_score_counts_correct_wrong_failed_and_not_run(tmp_path):
    score = golden_eval.score(
        golden_eval.read_golden(golden_file(tmp_path)),
        golden_eval.read_results(results_file(tmp_path, RESULTS)),
    )

    assert score["total"] == 4
    assert [row["company"] for row in score["not_run"]] == ["Delta"]
    assert score["run"] == 3
    assert score["answered"] == 2
    assert score["correct"] == 1
    assert score["accuracy"] == 0.5
    assert score["coverage"] == pytest.approx(2 / 3)
    assert [(w["company"], w["expected"], w["got"]) for w in score["wrong"]] == [("Beta", "B", "A")]
    assert score["wrong"][0]["reason"] == "Beta says it answers calls."
    assert [(f["company"], f["error"][:30]) for f in score["failed"]] == [("Gamma", "The model could not fill in in")]


def test_demo_agreement_only_cares_about_a_b_or_neither(tmp_path):
    golden = [("a1.example", "A1", "A"), ("c1.example", "C1", "C"), ("c2.example", "C2", "C"), ("b1.example", "B1", "B")]
    rows = [
        ["a1.example", "A1", "A", "r", "n", "", ""],  # right cluster, right demo
        ["c1.example", "C1", "E", "r", "n", "", ""],  # wrong cluster, but neither has a demo
        ["c2.example", "C2", "A", "r", "n", "", ""],  # wrong cluster and the voice demo would be sent
        ["b1.example", "B1", "A", "r", "n", "", ""],  # wrong cluster and the wrong demo
    ]
    score = golden_eval.score(
        golden_eval.read_golden(golden_file(tmp_path, golden)),
        golden_eval.read_results(results_file(tmp_path, rows)),
    )

    assert score["correct"] == 1
    assert score["demo_correct"] == 2
    assert score["demo_accuracy"] == 0.5


def test_the_report_shows_demo_agreement(tmp_path, capsys):
    golden_eval.main(["--golden", str(golden_file(tmp_path)), "--csv", str(results_file(tmp_path, RESULTS))])

    assert "same demo as the label (A, B or none): 1 of 2 answered (50%)" in capsys.readouterr().out


def test_score_counts_notes_and_guard_rejections_among_answered_rows(tmp_path):
    score = golden_eval.score(
        golden_eval.read_golden(golden_file(tmp_path)),
        golden_eval.read_results(results_file(tmp_path, RESULTS)),
    )

    assert score["with_note"] == 1
    assert score["note_rejected"] == 1


@pytest.mark.parametrize("url", ["https://www.Alpha.example/", "ALPHA.example", "http://alpha.example"])
def test_urls_match_however_they_were_written(tmp_path, url):
    rows = [[url, "Alpha", "A", "r", "n", "", ""]]
    score = golden_eval.score(
        golden_eval.read_golden(golden_file(tmp_path, GOLDEN[:1])),
        golden_eval.read_results(results_file(tmp_path, rows)),
    )

    assert score["correct"] == 1


def test_no_answered_rows_gives_no_accuracy_not_a_crash(tmp_path):
    rows = [["alpha.example", "Alpha", "", "", "", "", "Could not reach site"]]
    score = golden_eval.score(
        golden_eval.read_golden(golden_file(tmp_path, GOLDEN[:1])),
        golden_eval.read_results(results_file(tmp_path, rows)),
    )

    assert score["answered"] == 0
    assert score["accuracy"] is None


def test_the_report_says_where_the_numbers_came_from_and_lists_every_wrong_row(tmp_path, capsys):
    code = golden_eval.main(
        ["--golden", str(golden_file(tmp_path)), "--csv", str(results_file(tmp_path, RESULTS)), "--threshold", "0.9"]
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "no model was called now" in out
    assert "results.csv" in out
    assert "cluster accuracy: 1 of 2 answered (50%)" in out
    assert "Beta: expected B, got A" in out
    assert "Gamma" in out and "UNKNOWN" in out
    assert "Delta" in out and "not run" in out
    assert "BELOW" in out


def test_exit_code_is_zero_at_or_above_the_threshold(tmp_path, capsys):
    rows = [["alpha.example", "Alpha", "A", "r", "n", "", ""], ["beta.example", "Beta", "B", "r", "n", "", ""]]
    golden = golden_file(tmp_path, GOLDEN[:2])

    assert golden_eval.main(["--golden", str(golden), "--csv", str(results_file(tmp_path, rows)), "--threshold", "1.0"]) == 0
    assert "BELOW" not in capsys.readouterr().out


def test_an_empty_results_file_exits_2_with_a_message(tmp_path, capsys):
    code = golden_eval.main(["--golden", str(golden_file(tmp_path)), "--csv", str(results_file(tmp_path, []))])

    assert code == 2
    assert "no rows" in capsys.readouterr().out


def test_a_missing_results_file_exits_2_with_a_message(tmp_path, capsys):
    code = golden_eval.main(["--golden", str(golden_file(tmp_path)), "--csv", str(tmp_path / "nope.csv")])

    assert code == 2
    assert "cannot read" in capsys.readouterr().out


def test_the_committed_golden_file_is_well_formed():
    rows = golden_eval.read_golden(ROOT / "evals" / "golden.csv")

    assert len(rows) >= 30
    assert len({golden_eval.url_key(row["url"]) for row in rows}) == len(rows)
    assert {row["expected_cluster"] for row in rows} <= set("ABCDEFG")
    assert all(row["label_source"] for row in rows)
