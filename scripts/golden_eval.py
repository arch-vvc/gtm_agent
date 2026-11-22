"""Score the engine's cluster answers against hand set labels, from a results CSV.

    uv run python -m scripts.golden_eval --csv results/eval_results.csv --floor-file evals/floor.json

This reads a CSV that scripts.real_run wrote from a real model run (or the public copy of it
that scripts.export_public writes, which has no note text). It calls no model and needs no keys.
To refresh the numbers, run real_run over the golden companies first:

    cut -d, -f1 evals/golden.csv | tail -n +2 > targets.txt

The labels in evals/golden.csv are the Cluster column of the author's tracker, set before the
engine existed. The headline metric is demo choice: does the engine pick the same demo (A, B or
none) as the label. That is what decides what gets sent. Cluster accuracy is reported too, against
a 90% target, but only informs.

Exit code: 0 when every floor holds (or no floor was asked for), 1 when demo choice is below the
floor in --floor-file (or cluster accuracy is below an explicit --threshold), 2 when a CSV could
not be read.
"""

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.csv"
DEFAULT_THRESHOLD = 0.9  # the cluster accuracy target, shown for information
CLUSTERS = list("ABCDEFG")
DEMOS = ["A", "B", "none"]


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


def read_floor(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def has_note(row):
    """A full CSV has the note text, the public CSV only has a has_note flag."""
    return bool(row.get("pitch_note")) or (row.get("has_note") or "").strip().lower() == "true"


def score(golden, results):
    """Compare each golden row with its result row. Rows with no result were not run."""
    out = {"total": len(golden), "not_run": [], "failed": [], "wrong": [], "answered": 0, "correct": 0,
           "demo_correct": 0, "with_note": 0, "note_rejected": 0}  # fmt: skip
    out["confusion"] = {expected: dict.fromkeys([*CLUSTERS, "fail"], 0) for expected in CLUSTERS}
    out["confusion3"] = {expected: dict.fromkeys(DEMOS, 0) for expected in DEMOS}
    held_out = {"answered": 0, "demo_correct": 0}
    for entry in golden:
        row = results.get(url_key(entry["url"]))
        if row is None:
            out["not_run"].append(entry)
            continue
        expected = entry["expected_cluster"].strip().upper()
        got = (row.get("cluster") or "").strip().upper()
        if row.get("error") or not got:
            out["failed"].append({"company": entry["company"], "error": row.get("error") or "no cluster in the row"})
            if expected in out["confusion"]:
                out["confusion"][expected]["fail"] += 1
            continue
        out["answered"] += 1
        out["with_note"] += has_note(row)
        out["note_rejected"] += bool(row.get("pitch_error"))
        demo_match = demo_of(got) == demo_of(expected)
        out["demo_correct"] += demo_match
        if expected in out["confusion"] and got in out["confusion"][expected]:
            out["confusion"][expected][got] += 1
        out["confusion3"][demo_of(expected)][demo_of(got)] += 1
        if (entry.get("split") or "dev").strip() == "held_out":
            held_out["answered"] += 1
            held_out["demo_correct"] += demo_match
        if got == expected:
            out["correct"] += 1
        else:
            out["wrong"].append({"company": entry["company"], "expected": entry["expected_cluster"], "got": got,
                                 "reason": row.get("cluster_reason") or ""})  # fmt: skip
    held_out["demo_accuracy"] = held_out["demo_correct"] / held_out["answered"] if held_out["answered"] else None
    out["held_out"] = held_out
    out["run"] = out["total"] - len(out["not_run"])
    out["accuracy"] = out["correct"] / out["answered"] if out["answered"] else None
    out["demo_accuracy"] = out["demo_correct"] / out["answered"] if out["answered"] else None
    out["coverage"] = out["answered"] / out["run"] if out["run"] else None
    return out


def demo_line(correct, answered):
    if not answered:
        return "demo choice (A, B or none): none, no company was answered"
    return f"demo choice (A, B or none): {correct} of {answered} answered ({round(correct / answered * 100)}%)"


def matrix_lines(matrix, columns):
    width = 6
    lines = [" " * width + "".join(f"{column:>5}" for column in columns)]
    for expected, counts in matrix.items():
        lines.append(f"{expected:<{width}}" + "".join(f"{counts[column]:>5}" for column in columns))
    return lines


def report(result, csv_path, threshold=DEFAULT_THRESHOLD):
    lines = [
        f"Scored from {csv_path}: a real model run made earlier, no model was called now.",
        f"Golden set: {result['total']} companies, labels from the tracker's Cluster column.",
        (
            f"Run: {result['run']} of {result['total']} ({len(result['not_run'])} not run). "
            f"Answered: {result['answered']}. Failed: {len(result['failed'])}."
        ),
        demo_line(result["demo_correct"], result["answered"]),
    ]
    if result["accuracy"] is None:
        lines.append("cluster accuracy: none, no company was answered")
    else:
        percent = round(result["accuracy"] * 100)
        verdict = "" if result["accuracy"] >= threshold else f"   BELOW the {round(threshold * 100)}% target"
        lines.append(f"cluster accuracy: {result['correct']} of {result['answered']} answered ({percent}%){verdict}")
    lines.append(f"notes: {result['with_note']} produced, {result['note_rejected']} rejected by the guard (of the answered)")
    lines += ["", "Confusion matrix (rows expected, columns got)"]
    lines += matrix_lines(result["confusion"], [*CLUSTERS, "fail"])
    lines += ["", "Demo matrix (rows expected, columns got)"]
    lines += matrix_lines(result["confusion3"], DEMOS)
    held = result["held_out"]
    lines += ["", f"Held out (n={held['answered']} answered), kept apart from tuning", demo_line(held["demo_correct"], held["answered"])]
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


def floor_failures(result, floor):
    """Messages for every floor that does not hold. The held out floor needs min_held_out_n answered rows."""
    failures = []
    demo = result["demo_accuracy"]
    if demo is None or demo < floor["demo_choice"]:
        shown = "none" if demo is None else f"{demo:.1%}"
        failures.append(f"BELOW FLOOR: demo choice {shown} is under the floor of {floor['demo_choice']:.0%}")
    held = result["held_out"]
    if held["answered"] >= floor.get("min_held_out_n", 5) and held["demo_accuracy"] < floor["held_out_demo_choice"]:
        failures.append(
            f"BELOW FLOOR: held out demo choice {held['demo_accuracy']:.1%} (n={held['answered']}) "
            f"is under the floor of {floor['held_out_demo_choice']:.0%}"
        )
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score cluster answers in a real_run CSV against the golden labels.")
    parser.add_argument("--csv", required=True, help="results CSV written by scripts.real_run or scripts.export_public")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN), help="golden labels CSV")
    parser.add_argument("--floor-file", help="JSON with the demo choice floors, exit 1 when one is not met")
    parser.add_argument("--threshold", type=float, help="also exit 1 when cluster accuracy is below this")
    args = parser.parse_args(argv)

    try:
        golden = read_golden(args.golden)
        results = read_results(args.csv)
        floor = read_floor(args.floor_file) if args.floor_file else None
    except (OSError, KeyError, ValueError, csv.Error) as exc:
        print(f"cannot read the input files: {exc}")
        return 2
    if not results:
        print(f"{args.csv} has no rows, run scripts.real_run first")
        return 2

    result = score(golden, results)
    print(report(result, args.csv, args.threshold or DEFAULT_THRESHOLD))
    failures = floor_failures(result, floor) if floor else []
    if args.threshold is not None and (result["accuracy"] is None or result["accuracy"] < args.threshold):
        failures.append(f"BELOW the cluster accuracy threshold of {args.threshold:.0%}")
    if failures:
        print("\n" + "\n".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
