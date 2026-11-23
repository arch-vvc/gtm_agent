import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The 7 golden companies the engine had never been run on when the split was fixed.
NEVER_RUN = {"alguna", "nango", "pinelabs", "gushwork", "mactores", "kusho", "trylunar"}


def test_split_column_and_unrun_are_held_out():
    with open(ROOT / "evals" / "golden.csv", encoding="utf-8", newline="") as handle:
        golden = list(csv.DictReader(handle))

    assert len(golden) == 38
    assert {row["split"] for row in golden} <= {"dev", "held_out"}
    assert sum(row["split"] == "held_out" for row in golden) >= 10
    assert len({row["url"] for row in golden}) == 38  # one split per company, so none sits in both
    unrun = [row for row in golden if any(name in row["url"].lower() for name in NEVER_RUN)]
    assert len(unrun) == 7
    assert all(row["split"] == "held_out" for row in unrun)
