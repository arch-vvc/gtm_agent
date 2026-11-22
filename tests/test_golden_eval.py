import csv
import json
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

    assert "demo choice (A, B or none): 1 of 2 answered (50%)" in capsys.readouterr().out


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


# ---- demo choice headline, confusion matrix, held out split, floor gate ----

SPLIT_GOLDEN_HEADER = ["url", "company", "expected_cluster", "label_source", "split"]


def split_golden(tmp_path, rows):
    """rows are (url, company, expected, split). Everything here is SYNTHETIC."""
    return write(tmp_path / "golden.csv", SPLIT_GOLDEN_HEADER, [[u, n, c, "test", s] for u, n, c, s in rows])


def floor_file(tmp_path, **override):
    floor = {"demo_choice": 0.85, "held_out_demo_choice": 0.75, "min_held_out_n": 5} | override
    path = tmp_path / "floor.json"
    path.write_text(json.dumps(floor), encoding="utf-8")
    return path


def test_headline_is_demo_choice(tmp_path, capsys):
    code = golden_eval.main(["--golden", str(golden_file(tmp_path)), "--csv", str(results_file(tmp_path, RESULTS))])
    lines = capsys.readouterr().out.splitlines()
    metric = [line for line in lines if line.startswith(("demo choice", "cluster accuracy"))]

    assert code == 0  # no floor file and no explicit threshold, so the report is informational
    assert metric[0] == "demo choice (A, B or none): 1 of 2 answered (50%)"
    assert metric[1].startswith("cluster accuracy: 1 of 2 answered (50%)   BELOW the 90% target")


def test_confusion_matrix_counts(tmp_path, capsys):
    golden = [("a.example", "A1", "A"), ("b.example", "B1", "B"), ("c.example", "C1", "C"), ("d.example", "D1", "D")]
    rows = [
        ["a.example", "A1", "A", "r", "n", "", ""],
        ["b.example", "B1", "A", "r", "n", "", ""],
        ["c.example", "C1", "E", "r", "n", "", ""],
        ["d.example", "D1", "", "", "", "", "Could not reach site"],
    ]
    args = ["--golden", str(golden_file(tmp_path, golden)), "--csv", str(results_file(tmp_path, rows))]
    score = golden_eval.score(golden_eval.read_golden(args[1]), golden_eval.read_results(args[3]))

    assert score["confusion"]["A"]["A"] == 1
    assert score["confusion"]["B"]["A"] == 1
    assert score["confusion"]["C"]["E"] == 1
    assert score["confusion"]["D"]["fail"] == 1
    assert score["confusion3"]["B"]["A"] == 1
    assert score["confusion3"]["none"]["none"] == 1

    golden_eval.main(args)
    out = capsys.readouterr().out
    assert "Confusion matrix (rows expected, columns got)" in out
    header = out.split("Confusion matrix (rows expected, columns got)")[1].splitlines()[1].split()
    assert header[:7] == list("ABCDEFG")


def test_held_out_reported_separately(tmp_path, capsys):
    golden = [
        ("a.example", "A1", "A", "dev"),
        ("b.example", "B1", "B", "dev"),
        ("c.example", "C1", "A", "held_out"),
        ("d.example", "D1", "B", "held_out"),
    ]
    rows = [
        ["a.example", "A1", "A", "r", "n", "", ""],
        ["b.example", "B1", "B", "r", "n", "", ""],
        ["c.example", "C1", "A", "r", "n", "", ""],
        ["d.example", "D1", "A", "r", "n", "", ""],
    ]
    args = ["--golden", str(split_golden(tmp_path, golden)), "--csv", str(results_file(tmp_path, rows))]
    score = golden_eval.score(golden_eval.read_golden(args[1]), golden_eval.read_results(args[3]))

    assert score["held_out"]["answered"] == 2
    assert score["held_out"]["demo_correct"] == 1

    golden_eval.main(args)
    out = capsys.readouterr().out
    assert out.index("demo choice (A, B or none): 3 of 4") < out.index("Confusion matrix") < out.index("Held out (n=2")
    assert "demo choice (A, B or none): 1 of 2 answered (50%)" in out.split("Held out (n=2")[1]


def test_below_floor_exits_1(tmp_path, capsys):
    rows = [["alpha.example", "Alpha", "A", "r", "n", "", ""], ["beta.example", "Beta", "A", "r", "n", "", ""]]
    args = ["--golden", str(golden_file(tmp_path, GOLDEN[:2])), "--csv", str(results_file(tmp_path, rows))]

    assert golden_eval.main([*args, "--floor-file", str(floor_file(tmp_path))]) == 1
    assert "BELOW FLOOR" in capsys.readouterr().out
    assert golden_eval.main([*args, "--floor-file", str(floor_file(tmp_path, demo_choice=0.5))]) == 0
    assert "BELOW FLOOR" not in capsys.readouterr().out


def test_held_out_floor_needs_min_n_answered(tmp_path, capsys):
    golden = [("a.example", "A1", "A", "held_out"), ("b.example", "B1", "B", "held_out")]
    rows = [["a.example", "A1", "B", "r", "n", "", ""], ["b.example", "B1", "A", "r", "n", "", ""]]
    args = ["--golden", str(split_golden(tmp_path, golden)), "--csv", str(results_file(tmp_path, rows))]

    # demo choice is 0 of 2, so with the main floor at 0 only the held out floor can fail, and it is skipped at n=2.
    assert golden_eval.main([*args, "--floor-file", str(floor_file(tmp_path, demo_choice=0.0))]) == 0
    assert golden_eval.main([*args, "--floor-file", str(floor_file(tmp_path, demo_choice=0.0, min_held_out_n=2))]) == 1
    assert "BELOW FLOOR" in capsys.readouterr().out


def test_public_csv_without_notes_still_scores(tmp_path):
    header = ["url", "name", "cluster", "demo", "hiring_fde", "cluster_reason", "model", "error", "has_note", "pitch_error"]
    rows = [["alpha.example", "Alpha", "A", "d", "true", "r", "m", "", "true", ""]]
    score = golden_eval.score(
        golden_eval.read_golden(golden_file(tmp_path, GOLDEN[:1])),
        golden_eval.read_results(write(tmp_path / "p.csv", header, rows)),
    )

    assert score["with_note"] == 1
