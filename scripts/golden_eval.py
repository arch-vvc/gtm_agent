"""Score the engine's cluster answers against hand set labels, from a results CSV.

    uv run python -m scripts.golden_eval --csv results/real_results.csv

This reads a CSV that scripts.real_run wrote from a real model run. It calls no model
and needs no keys. To refresh the numbers, run real_run over the golden companies first:

    cut -d, -f1 evals/golden.csv | tail -n +2 > targets.txt

The labels in evals/golden.csv are the Cluster column of the author's tracker, set before the
engine existed. Exit code 0 means accuracy reached the threshold, 1 means it did not,
2 means the CSV could not be read.
"""

import argparse
import csv
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.csv"
DEFAULT_THRESHOLD = 0.9


def url_key(url):
    """Host and path in lower case, with no scheme, no www and no trailing slash."""
    text = (url or "").strip().lower()
    parsed = urlparse(text if "://" in text else "//" + text)
    return (parsed.netloc.removeprefix("www.") + parsed.path).rstrip("/")


def demo_of(cluster):
    """Only clusters A and B have a demo built. Every other cluster means no demo to send."""
    return cluster if cluster in ("A", "B") else "none"


def read_golden(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_results(path):
    """Rows of a real_run CSV keyed by url_key."""
    with open(path, encoding="utf-8", newline="") as handle:
        return {url_key(row["url"]): row for row in csv.DictReader(handle) if row.get("url")}


def score(golden, results):
    """Compare each golden row with its result row. Rows with no result were not run."""
    out = {"total": len(golden), "not_run": [], "failed": [], "wrong": [], "answered": 0, "correct": 0,
           "demo_correct": 0, "with_note": 0, "note_rejected": 0}  # fmt: skip
    for entry in golden:
        row = results.get(url_key(entry["url"]))
        if row is None:
            out["not_run"].append(entry)
            continue
        got = (row.get("cluster") or "").strip().upper()
        if row.get("error") or not got:
            out["failed"].append({"company": entry["company"], "error": row.get("error") or "no cluster in the row"})
            continue
        out["answered"] += 1
        out["with_note"] += bool(row.get("pitch_note"))
        out["note_rejected"] += bool(row.get("pitch_error"))
        expected = entry["expected_cluster"].strip().upper()
        out["demo_correct"] += demo_of(got) == demo_of(expected)
        if got == expected:
            out["correct"] += 1
        else:
            out["wrong"].append({"company": entry["company"], "expected": entry["expected_cluster"], "got": got,
                                 "reason": row.get("cluster_reason") or ""})  # fmt: skip
    out["run"] = out["total"] - len(out["not_run"])
    out["accuracy"] = out["correct"] / out["answered"] if out["answered"] else None
    out["demo_accuracy"] = out["demo_correct"] / out["answered"] if out["answered"] else None
    out["coverage"] = out["answered"] / out["run"] if out["run"] else None
    return out


def report(result, csv_path, threshold):
    lines = [
        f"Scored from {csv_path}: a real model run made earlier, no model was called now.",
        f"Golden set: {result['total']} companies, labels from the tracker's Cluster column.",
        (
            f"Run: {result['run']} of {result['total']} ({len(result['not_run'])} not run). "
            f"Answered: {result['answered']}. Failed: {len(result['failed'])}."
        ),
    ]
    if result["accuracy"] is None:
        lines.append("cluster accuracy: none, no company was answered")
    else:
        percent = round(result["accuracy"] * 100)
        verdict = "" if result["accuracy"] >= threshold else f"   BELOW the {round(threshold * 100)}% target"
        lines.append(f"cluster accuracy: {result['correct']} of {result['answered']} answered ({percent}%){verdict}")
    if result["demo_accuracy"] is not None:
        percent = round(result["demo_accuracy"] * 100)
        lines.append(
            f"same demo as the label (A, B or none): {result['demo_correct']} of {result['answered']} answered ({percent}%)"
        )
    lines.append(f"notes: {result['with_note']} produced, {result['note_rejected']} rejected by the guard (of the answered)")
    if result["wrong"]:
        lines.append("\nWrong clusters:")
        lines += [f"  {w['company']}: expected {w['expected']}, got {w['got']}. {w['reason'][:140]}" for w in result["wrong"]]
    if result["failed"]:
        lines.append("\nFailed before a cluster:")
        lines += [f"  {f['company']}: {f['error'][:140]}" for f in result["failed"]]
    if result["not_run"]:
        lines.append("\nNot run:")
        lines += [f"  {entry['company']} (not run)" for entry in result["not_run"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score cluster answers in a real_run CSV against the golden labels.")
    parser.add_argument("--csv", required=True, help="results CSV written by scripts.real_run")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN), help="golden labels CSV")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="accuracy needed for exit code 0")
    args = parser.parse_args(argv)

    try:
        golden = read_golden(args.golden)
        results = read_results(args.csv)
    except (OSError, KeyError, csv.Error) as exc:
        print(f"cannot read the CSV files: {exc}")
        return 2
    if not results:
        print(f"{args.csv} has no rows, run scripts.real_run first")
        return 2

    result = score(golden, results)
    print(report(result, args.csv, args.threshold))
    return 0 if result["accuracy"] is not None and result["accuracy"] >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
