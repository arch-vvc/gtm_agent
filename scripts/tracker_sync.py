"""Run the pitch engine over a tracker and write a ranked CSV of drafts.

    uv run python -m scripts.tracker_sync FDE_Startup_Tracker.xlsx --domains evals/golden.csv --out results/ranked.csv

Reads the tracker (an .xlsx with one or more sheets, or a .csv), finds each company's website,
runs the engine once per company (with the job post link from the tracker's Link column when it is
a Greenhouse, Lever or Ashby link) and writes one row per tracker row: the answer, the draft note,
the evidence quotes and a rank. It never edits the tracker and never sends anything.

The website comes from a Website column in the tracker if there is one, otherwise from a domains CSV
with columns company and url (evals/golden.csv has them). A company with no website is listed as
"no website" and skipped, never guessed.

Rank (only rows with a note are ranked, highest first, ties in tracker order):
    demo built (cluster A or B)   +3
    a note passed the guard       +2
    tracker "Fresher fit" Good    +2
    careers page lists an FDE role +1
    engine cluster = tracker cluster +1
The reason is written next to every score. The rule is a plain sum, so change it by editing score_row.
"""

import argparse
import csv
import re
from pathlib import Path

import scrape
from scripts.golden_eval import url_key

OUTPUT_COLUMNS = [
    "rank", "score", "company", "role", "location", "setup", "fresher_fit", "status", "tracker_cluster",
    "engine_cluster", "cluster_agrees", "demo", "hiring_fde", "url", "job_url", "pitch_note", "evidence",
    "pitch_error", "error", "rank_reason",
]  # fmt: skip
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
BUILT_NO_DEMO = ("", "none built", "none")
DEFAULT_DELAY = 5.0


def company_key(name):
    """A company name in lower case without a YC batch suffix such as (YC W22)."""
    return re.sub(r"\s*\(yc[^)]*\)", "", name or "", flags=re.IGNORECASE).strip().lower()


def link_or_none(text):
    text = (text or "").strip()
    return text if text.lower().startswith("http") else None


def read_tracker(path):
    """Tracker rows as dicts keyed by the header names, plus job_url. A row with no Company is dropped."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return read_xlsx(path)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = [{**row, "job_url": link_or_none(row.get("Link"))} for row in csv.DictReader(handle)]
    return [row for row in rows if (row.get("Company") or "").strip()]


def read_xlsx(path):
    import openpyxl

    workbook = openpyxl.load_workbook(path)
    rows = []
    for sheet in workbook.worksheets:
        lines = list(sheet.iter_rows())
        if not lines:
            continue
        header = [str(cell.value).strip() if cell.value is not None else "" for cell in lines[0]]
        if "Company" not in header or "Link" not in header:
            continue  # not a tracker sheet, for example the how to use page
        link_at = header.index("Link")
        for line in lines[1:]:
            row = {name: ("" if cell.value is None else str(cell.value)) for name, cell in zip(header, line) if name}
            if not row.get("Company", "").strip():
                continue
            link_cell = line[link_at]
            target = link_cell.hyperlink.target if link_cell.hyperlink else None
            row["job_url"] = link_or_none(target) or link_or_none(row.get("Link"))
            rows.append(row)
    return rows


def read_domains(path):
    """company_key to website, from a CSV with the columns company and url."""
    with open(path, encoding="utf-8", newline="") as handle:
        return {company_key(row["company"]): row["url"].strip() for row in csv.DictReader(handle) if row.get("url")}


def build_targets(rows, domains):
    """Set row["url"] on every row that has a website. Returns ({url: job link or None}, rows with no website)."""
    targets = {}
    skipped = []
    for row in rows:
        url = (row.get("Website") or "").strip() or domains.get(company_key(row["Company"]))
        if not url:
            skipped.append(row)
            continue
        row["url"] = url
        job = row.get("job_url")
        # Only links the engine can read go in the targets file. Other links stay in the output column.
        if targets.get(url) is None:
            targets[url] = job if scrape.parse_job_url(job) else None
    return targets, skipped


def truthy(value):
    return str(value).strip().lower() == "true"


def score_row(row):
    """Return (points, reason). The rule is in the module docstring."""
    parts = []
    if (row.get("demo") or "").strip().lower() not in BUILT_NO_DEMO:
        parts.append(("demo built", 3))
    if row.get("pitch_note"):
        parts.append(("note", 2))
    if (row.get("Fresher fit") or "").strip().lower() == "good":
        parts.append(("fresher fit", 2))
    if truthy(row.get("hiring_fde")):
        parts.append(("hiring FDE", 1))
    if agrees(row) == "yes":
        parts.append(("cluster agrees", 1))
    return sum(points for _, points in parts), ", ".join(f"{name} +{points}" for name, points in parts)


def agrees(row):
    engine = (row.get("cluster") or "").strip().upper()
    mine = (row.get("Cluster") or "").strip()[:1].upper()
    if not engine or not mine:
        return ""
    return "yes" if engine == mine else "no"


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def status_of(row, raw):
    if not row.get("url"):
        return "no website"
    if raw is None:
        return "not run"
    if raw.get("error"):
        return "failed: " + raw["error"][:100]
    return "ready" if raw.get("pitch_note") else "no note"


def read_raw(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return {url_key(row["url"]): row for row in csv.DictReader(handle) if row.get("url")}


def build_output(rows, raw_by_key):
    """One output dict per tracker row. Ready rows first, ranked by score then tracker order."""
    out = []
    for position, row in enumerate(rows):
        raw = raw_by_key.get(url_key(row["url"])) if row.get("url") else None
        merged = {**row, **(raw or {})}
        status = status_of(row, raw)
        score, reason = score_row(merged) if status == "ready" else (0, "")
        out.append(
            {
                "score": score, "company": row["Company"], "role": row.get("Role", ""), "location": row.get("Location (as listed)", ""),
                "setup": row.get("Setup", ""), "fresher_fit": row.get("Fresher fit", ""), "status": status,
                "tracker_cluster": row.get("Cluster", ""), "engine_cluster": (raw or {}).get("cluster", ""),
                "cluster_agrees": agrees(merged), "demo": (raw or {}).get("demo", ""), "hiring_fde": (raw or {}).get("hiring_fde", ""),
                "url": row.get("url", ""), "job_url": row.get("job_url") or "", "pitch_note": (raw or {}).get("pitch_note", ""),
                "evidence": (raw or {}).get("evidence", ""), "pitch_error": (raw or {}).get("pitch_error", ""),
                "error": (raw or {}).get("error", ""), "rank_reason": reason, "_position": position,
            }
        )  # fmt: skip
    ready = sorted((o for o in out if o["status"] == "ready"), key=lambda o: (-o["score"], o["_position"]))
    rest = [o for o in out if o["status"] != "ready"]
    for rank, item in enumerate(ready, start=1):
        item["rank"] = rank
    return ready + rest


def write_output(path, items):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OUTPUT_COLUMNS)
        for item in items:
            writer.writerow([safe_cell(item.get(column, "")) for column in OUTPUT_COLUMNS])


def run_engine(targets_path, raw_csv, resume, delay):
    """Run scripts.real_run over the targets file. Tests replace this."""
    from scripts import real_run

    argv = ["--file", str(targets_path), "--csv", str(raw_csv), "--delay", str(delay)]
    return real_run.main(argv + (["--resume"] if resume else []))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the pitch engine over a tracker and write a ranked CSV of drafts.")
    parser.add_argument("tracker", help="the tracker, .xlsx or .csv (never changed)")
    parser.add_argument("--domains", help="CSV with columns company and url, used when the tracker has no Website column")
    parser.add_argument("--out", required=True, help="the ranked CSV to write")
    parser.add_argument("--resume", action="store_true", help="skip companies that already have a row without an error")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="seconds to wait between companies")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    if out_path.resolve() == Path(args.tracker).resolve():
        print("refusing to run: --out would overwrite the tracker")
        return 2
    try:
        rows = read_tracker(args.tracker)
        domains = read_domains(args.domains) if args.domains else {}
    except (OSError, KeyError, csv.Error) as exc:
        print(f"cannot read the tracker or domains file: {exc}")
        return 2

    targets, skipped = build_targets(rows, domains)
    with_job = sum(1 for job in targets.values() if job)
    print(f"{len(rows)} tracker rows, {len(targets)} companies to run, {with_job} with a job link")
    if skipped:
        print("no website: " + ", ".join(dict.fromkeys(row["Company"] for row in skipped)))
    if args.dry_run:
        return 0
    if not targets:
        print("nothing to run: no row has a website")
        return 2

    targets_path = out_path.with_suffix(".targets.txt")
    raw_csv = out_path.with_suffix(".raw.csv")
    targets_path.parent.mkdir(parents=True, exist_ok=True)
    targets_path.write_text("\n".join(f"{url} {job}" if job else url for url, job in targets.items()) + "\n", encoding="utf-8")

    run_engine(targets_path, raw_csv, args.resume, args.delay)
    try:
        raw_by_key = read_raw(raw_csv)
    except OSError as exc:
        print(f"the engine wrote no results CSV: {exc}")
        return 2

    items = build_output(rows, raw_by_key)
    write_output(out_path, items)
    ready = sum(1 for item in items if item["status"] == "ready")
    print(f"\nWrote {len(items)} rows to {out_path} ({ready} ready, ranked). The tracker was not changed and nothing was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
