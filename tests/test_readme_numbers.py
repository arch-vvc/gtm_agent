"""The README and docs/EVAL.md quote the eval numbers. They must equal what scripts.golden_eval computes."""

import re
from pathlib import Path

from scripts import golden_eval

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
EVAL_DOC = (ROOT / "docs" / "EVAL.md").read_text(encoding="utf-8")


def current_score():
    golden = golden_eval.read_golden(golden_eval.DEFAULT_GOLDEN)
    results = golden_eval.read_results(ROOT / "results" / "eval_results.csv")
    return golden_eval.score(golden, results)


def cluster_line(result):
    percent = round(result["accuracy"] * 100)
    return f"cluster accuracy: {result['correct']} of {result['answered']} answered ({percent}%)"


def test_readme_numbers_match_eval():
    result = current_score()
    assert golden_eval.demo_line(result["demo_correct"], result["answered"]) in README
    assert cluster_line(result) in README
    assert "90% target" in README
    for line in golden_eval.matrix_lines(result["confusion3"], golden_eval.DEMOS):
        assert line in README


def test_readme_names_the_commit_behind_the_numbers():
    match = re.search(r"commit `([0-9a-f]{7,40})`", README)
    assert match, "the README must name the commit that produced the saved run"


def test_eval_doc_holds_the_full_matrix_and_the_known_limits():
    result = current_score()
    for line in golden_eval.matrix_lines(result["confusion"], [*golden_eval.CLUSTERS, "fail"]):
        assert line in EVAL_DOC
    assert golden_eval.demo_line(result["demo_correct"], result["answered"]) in EVAL_DOC
    assert cluster_line(result) in EVAL_DOC
    held = result["held_out"]
    assert f"only {held['answered']} of the 10 held out rows are answered" in EVAL_DOC
    assert "fixed after seeing results" in EVAL_DOC
    assert "older than the code" in EVAL_DOC
    assert "missed 4 of 5 paraphrased latency claims (80%)" in EVAL_DOC
    assert "known limit" in EVAL_DOC
