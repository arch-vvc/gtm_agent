"""Write the public copy of a real_run CSV: the engine's answers with no note text.

    uv run python -m scripts.export_public --csv results/real_results.csv --out results/eval_results.csv

The full CSV holds machine written outreach notes about named companies, so it stays private.
The public copy keeps what the eval needs (cluster, demo, reason, errors) and only says whether a
note exists. It drops pitch_note, customer_pain, tailoring and evidence.
"""

import argparse
import csv

PUBLIC_COLUMNS = ["url", "name", "cluster", "demo", "hiring_fde", "cluster_reason", "model", "error", "has_note",
                  "pitch_error"]  # fmt: skip


def public_row(row):
    out = {column: row.get(column) or "" for column in PUBLIC_COLUMNS}
    out["has_note"] = "true" if row.get("pitch_note") else "false"
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export a real_run CSV without any note or tailoring text.")
    parser.add_argument("--csv", default="results/real_results.csv", help="full results CSV")
    parser.add_argument("--out", default="results/eval_results.csv", help="public CSV to write")
    args = parser.parse_args(argv)

    try:
        with open(args.csv, encoding="utf-8", newline="") as handle:
            rows = [public_row(row) for row in csv.DictReader(handle) if row.get("url")]
    except OSError as exc:
        print(f"cannot read {args.csv}: {exc}")
        return 2
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PUBLIC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}, no note text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
