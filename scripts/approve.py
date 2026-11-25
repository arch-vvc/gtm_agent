"""Approve a pitch note by hand. Nothing is "ready" until a person runs this.

Usage from the repo root:

    uv run python -m scripts.approve --csv results/real_results.csv --url peakflo.co --by bobby
    uv run python -m scripts.approve --csv results/real_results.csv --url peakflo.co --revoke
    uv run python -m scripts.approve --csv results/real_results.csv --list-ready

Approving needs a note on that row and re runs the pitch guard on it first: style rules, claim
rules, the demo claim check against the fact sheet, and the rule that a cluster with no built demo
cannot claim one. The guard here has no site text, so the check that every name appears on the
site is not repeated; it already ran when the note was written. A row that fails stays
needs_review and the problems are printed.

The approval lives in the CSV only (approval_status, approved_by, approved_at). It is not sent
to Postgres or the API. scripts/real_run.py never writes "approved", and its --resume keeps
approved rows as they are.

Exit codes: 0 done, 1 refused (no note or the guard failed), 2 bad input (unknown URL, blank name,
missing file).
"""

import argparse
import csv
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import facts
import pitch
from scripts.real_run import url_key

APPROVAL_COLUMNS = ["approval_status", "approved_by", "approved_at"]
SHEETS = {"A": "call-qa", "B": "invoice-exception-triage"}


def model_label(row):
    """Which model wrote the note. Groq answers only when Gemini failed, so a Groq note is marked FALLBACK."""
    model = (row.get("model") or "").strip()
    if not model:
        return "model unknown"
    return model if model.startswith("gemini") else f"{model} FALLBACK, read it twice"


def guard_problems(row):
    """Why this row's note cannot be approved. An empty list means it passes."""
    note = (row.get("pitch_note") or "").strip()
    if not note:
        return ["row has no note"]
    problems = pitch.check_pitch_note(note) + pitch.check_pitch_claims(note)
    cluster = row.get("cluster")
    if cluster in SHEETS:
        problems += pitch.check_demo_claims(note, facts.load(SHEETS[cluster]))
    elif pitch.claims_built_demo(note):
        problems.append("claims a built demo for a cluster with no demo built")
    return problems


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    # An older CSV may lack the approval columns: add them, keep every other column as it is.
    for column in APPROVAL_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)
    for row in rows:
        row.setdefault("approval_status", "")
        if not row["approval_status"]:
            row["approval_status"] = "needs_review" if (row.get("pitch_note") or "").strip() else "no_note"
    return fieldnames, rows


def write_csv(path, fieldnames, rows):
    """Write to a temporary file in the same folder, then replace, so a crash never truncates the CSV."""
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve",
        description="Approve, revoke or list pitch notes in a real_run results CSV. CSV level only.",
    )
    parser.add_argument("--csv", required=True, metavar="PATH", help="the results CSV written by scripts.real_run")
    parser.add_argument("--url", help="the company row to approve or revoke (any written form of its URL)")
    parser.add_argument("--by", help="who approves; required with --url unless --revoke")
    parser.add_argument("--revoke", action="store_true", help="put the row back to needs_review and clear who and when")
    parser.add_argument("--list-ready", action="store_true", help="print the approved rows and stop")
    args = parser.parse_args(argv)
    if args.list_ready:
        return args
    if not args.url:
        parser.error("give --url, or --list-ready")
    if args.revoke and args.by:
        parser.error("--revoke does not take --by")
    return args


def main(argv=None):
    args = parse_args(argv)
    if not Path(args.csv).is_file():
        print(f"No such file: {args.csv}", file=sys.stderr)
        return 2
    fieldnames, rows = read_csv(args.csv)

    if args.list_ready:
        ready = [row for row in rows if row["approval_status"] == "approved" and (row.get("pitch_note") or "").strip()]
        for row in ready:
            print(f"{row['url']}\t{row.get('approved_by', '')}\t{row.get('approved_at', '')}\t{model_label(row)}")
        print(f"{len(ready)} approved of {len(rows)} rows")
        return 0

    matches = [row for row in rows if url_key(row["url"]) == url_key(args.url)]
    if not matches:
        print(f"No row for {args.url} in {args.csv}", file=sys.stderr)
        return 2
    row = matches[0]

    if args.revoke:
        row.update(approval_status="needs_review" if (row.get("pitch_note") or "").strip() else "no_note",
                   approved_by="", approved_at="")
        write_csv(args.csv, fieldnames, rows)
        print(f"Revoked {row['url']}: back to {row['approval_status']}")
        return 0

    approver = (args.by or "").strip()
    if not approver:
        print("--by needs a name", file=sys.stderr)
        return 2
    problems = guard_problems(row)
    if problems:
        label = "Refused, row has no note" if problems == ["row has no note"] else "Refused, the note fails the guard"
        print(f"{label} for {row['url']}:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    row.update(
        approval_status="approved",
        approved_by=approver,
        approved_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    write_csv(args.csv, fieldnames, rows)
    print(f"Approved {row['url']} by {approver} at {row['approved_at']} (note written by {model_label(row)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
