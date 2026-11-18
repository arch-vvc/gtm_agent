"""Run the pitch engine on real URLs, with real model calls, and print what comes back.

Usage from the repo root:

    python -m scripts.real_run [--provider gemini|groq|all] [--csv PATH] [--file PATH]
                               [--resume] [--delay SECONDS] [URL ...]

This calls enrich.enrich(url) directly. Nothing is written to Postgres and no job
is queued. With --csv PATH it also writes one row per URL (errors included) to a CSV
file. For every URL it prints the full result as JSON, then the pitch markdown
the API would serve, and a WARNING line when the grounding guard left pitch_note empty.

It needs GEMINI_API_KEY and GROQ_API_KEY in the environment; with either missing it
names it, says how to set it and exits 2. The Gemini path also
uses Redis for its model cooldowns, so run this inside the worker container, which
has the keys and a Redis next to it:

    docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run peakflo.co cekura.ai

Outside Docker, point REDIS_HOST at a Redis you can reach. The exit code is non zero
when any URL ended with an error. An exception on one URL, such as a bad API key or a
429, is printed as an ERROR line and the remaining URLs still run.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import pitch
from scrape import normalise_url


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="python -m scripts.real_run",
        description="Run enrich.enrich on real URLs and print the JSON and the pitch markdown. No database write.",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "groq", "all"],
        default="all",
        help="which model provider to use (default: all, Gemini first then Groq)",
    )
    parser.add_argument(
        "--csv",
        metavar="PATH",
        help=(
            "also write one row per URL, errors included, to this CSV file (parent folders are created; "
            "an existing file is overwritten). Text that starts with = + - @ gets a leading apostrophe "
            "so spreadsheets do not run it as a formula."
        ),
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help=(
            "read URLs from this text file, one per line. Blank lines and lines starting with # are ignored. "
            "Combined with any URLs given as arguments; duplicates are dropped and the first is kept."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "needs --csv. When the CSV already exists, skip URLs that have a row with no error, "
            "retry the rest and keep the finished rows."
        ),
    )
    parser.add_argument(
        "--delay",
        metavar="SECONDS",
        type=float,
        default=DEFAULT_DELAY,
        help=f"wait this long between companies so a long list stays inside the free tiers (default: {DEFAULT_DELAY:g})",
    )
    parser.add_argument("urls", metavar="URL", nargs="*", help="company website, for example peakflo.co")
    args = parser.parse_args(argv)
    if args.csv and Path(args.csv).is_dir():
        parser.error(f"--csv {args.csv} is a directory, give a file path")
    if args.resume and not args.csv:
        parser.error("--resume needs --csv, so there is a file to resume from")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    file_urls = []
    args.job_urls = {}
    if args.file:
        try:
            targets = read_targets(args.file)
            file_urls = dedupe_urls(list(targets))
            args.job_urls = {url_key(url): job for url, job in targets.items() if job}
        except OSError as exc:
            parser.error(f"cannot read --file {args.file}: {exc.strerror or exc}")
        if not file_urls:
            parser.error(f"--file {args.file} has no URLs (only blank lines and comments)")
    args.urls = dedupe_urls(args.urls + file_urls)
    if not args.urls:
        parser.error("give at least one URL, or --file PATH")
    return args


def url_key(url):
    """Normalised form used to spot duplicates and finished rows."""
    return normalise_url(url) or url.strip().lower()


def dedupe_urls(urls):
    seen = set()
    kept = []
    for url in urls:
        key = url_key(url)
        if key not in seen:
            seen.add(key)
            kept.append(url)
    return kept


def read_targets(path):
    """Targets from a text file as {company url: job post url or None}.

    One per line: the company, then optionally a job post link after whitespace. Blank lines
    and # comments are ignored, and a repeated company keeps its first line.
    """
    with open(path, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle]
    targets = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        targets.setdefault(parts[0], parts[1] if len(parts) > 1 else None)
    return targets


def read_url_file(path):
    """URLs from a text file: one per line, blanks and # comments ignored, duplicates dropped."""
    return dedupe_urls(list(read_targets(path)))


def read_finished_rows(path):
    """Rows of an existing results CSV that have no error, as lists in CSV_COLUMNS order."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    return [[record.get(column, "") for column in CSV_COLUMNS] for record in records if record.get("url") and not record.get("error")]


def choose_providers(enrich, provider):
    if provider == "gemini":
        return [enrich.ask_gemini]
    if provider == "groq":
        return [enrich.ask_groq]
    return [enrich.ask_gemini, enrich.ask_groq]


def provider_of(model):
    if model is None:
        return None
    return "gemini" if model.startswith("gemini") else "groq"


def result_as_json(out):
    company = out["company"]
    return {
        "name": out["name"],
        "company": company.model_dump() if company else None,
        "demo": out["demo"],
        "model": out["model"],
        "pitch_note": out["pitch_note"],
        "pitch_error": out["pitch_error"],
        "careers_url": out["careers_url"],
        "hiring_fde": out["hiring_fde"],
        "error": out["error"],
    }


def markdown_row(out):
    """Build the row render_pitch_markdown expects from the enrich result."""
    company = out["company"]
    return {
        "name": out["name"],
        "cluster": company.cluster,
        "demo": out["demo"],
        "hiring_fde": out["hiring_fde"],
        "pitch_note": out["pitch_note"],
        "tailoring": company.tailoring,
    }


CSV_COLUMNS = [
    "url",
    "name",
    "cluster",
    "demo",
    "hiring_fde",
    "cluster_reason",
    "customer_pain",
    "tailoring",
    "pitch_note",
    "pitch_error",
    "model",
    "error",
    "evidence",
]


DEFAULT_DELAY = 5

SECRET_ENV_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
SECRET_SHAPES = [
    re.compile(r"sk-[A-Za-z0-9_-]{6,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{10,}"),
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"),
]
SECRET_HEADER = re.compile(
    r"(authorization|x-goog-api-key)(\s*:\s*)(?:(?:Bearer|Basic|Token)\s+)?[^\s,;'\"]+",
    re.IGNORECASE,
)
MAX_MESSAGE_LENGTH = 300


def safe_message(exc):
    """Return 'ClassName: message' with secrets removed, on one line, at most 300 characters.

    SDK errors can echo request headers or keys, so this text is the only form of an
    exception that may be printed or written to a file.
    """
    text = f"{type(exc).__name__}: {exc}"
    secrets = [v for name, v in os.environ.items() if any(w in name.upper() for w in SECRET_ENV_WORDS)]
    for value in sorted((v for v in secrets if len(v) >= 6), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    for shape in SECRET_SHAPES:
        text = shape.sub("[REDACTED]", text)
    text = SECRET_HEADER.sub(r"\1\2[REDACTED]", text)
    return " ".join(text.split())[:MAX_MESSAGE_LENGTH]


def cell(value):
    """One CSV cell: None is empty, booleans are true or false, everything else is text.

    Text starting with = + - @ tab or carriage return gets a leading apostrophe so a
    spreadsheet shows it as text instead of running it as a formula.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text and text[0] in "=+-@\t\r":
        return "'" + text
    return text


def csv_row(url, out=None, error=None):
    """Build the CSV row for one URL. Pass out for an enrich result, error for an exception."""
    row = {"url": url, "error": error}
    if out is not None:
        company = out["company"]
        row.update(
            name=out["name"],
            demo=out["demo"],
            hiring_fde=out["hiring_fde"],
            pitch_note=out["pitch_note"],
            pitch_error=out["pitch_error"],
            model=out["model"],
            error=out["error"],
            evidence=" | ".join(out.get("evidence") or []),
        )
        if company:
            row.update(
                cluster=company.cluster,
                cluster_reason=company.cluster_reason,
                customer_pain=company.customer_pain,
                tailoring=" | ".join(company.tailoring),
            )
    return [cell(row.get(column)) for column in CSV_COLUMNS]


def write_csv(path, rows, announce=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)
    if announce:
        print(f"\nCSV written to {path} ({len(rows)} rows)")


def run_one(enrich, url, rows, job_url=None):
    """Enrich one URL, print everything and add its CSV row to rows. Returns True when it worked."""
    print(f"\n===== {url} =====")
    try:
        out = enrich.enrich(url, job_url=job_url) if job_url else enrich.enrich(url)
    except Exception as exc:  # noqa: BLE001
        # Blind except on purpose: one bad URL must not stop the run.
        # The message is redacted first: SDK errors can echo keys or headers.
        message = safe_message(exc)
        print(f"ERROR: {message}")
        rows.append(csv_row(url, error=message))
        return False

    rows.append(csv_row(url, out=out))
    print(json.dumps(result_as_json(out), indent=2, ensure_ascii=False))

    if out["error"]:
        print(f"ERROR: {out['error']}")
        return False

    print(f"\nAnswered by provider {provider_of(out['model'])}, model {out['model']}")
    print("\n----- pitch markdown -----")
    print(pitch.render_pitch_markdown(markdown_row(out)))

    if out["pitch_note"] is None:
        print(f"WARNING: pitch_note is NULL. pitch_error: {out['pitch_error']}")
    return True


def missing_keys():
    """Names of the model keys that are not set. enrich builds both clients on import, so both are needed."""
    gemini = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    groq = os.environ.get("GROQ_API_KEY", "").strip()
    return [name for name, value in (("GEMINI_API_KEY", gemini), ("GROQ_API_KEY", groq)) if not value]


def report_missing_keys(missing):
    lines = [
        f"Missing: {', '.join(missing)}",
        "This script needs both GEMINI_API_KEY and GROQ_API_KEY: Gemini answers first and Groq is the fallback,",
        "and both clients are built when it starts. Set them in your shell, then run it again:",
        "",
        "    export GEMINI_API_KEY=your-gemini-key",
        "    export GROQ_API_KEY=your-groq-key",
        "",
        "Or run inside Docker, which reads them from .env: docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run URL",
    ]
    print("\n".join(lines), file=sys.stderr)


def main(argv=None):
    args = parse_args(argv)

    missing = missing_keys()
    if missing:
        report_missing_keys(missing)
        return 2

    # Imported here because importing enrich builds the Gemini and Groq clients,
    # which need API keys. --help must work without them.
    import enrich

    enrich.PROVIDERS = choose_providers(enrich, args.provider)

    rows = []
    todo = args.urls
    if args.resume:
        rows = read_finished_rows(args.csv)
        finished = {url_key(row[0]) for row in rows}
        todo = [url for url in args.urls if url_key(url) not in finished]
        print(f"Resuming: {len(args.urls) - len(todo)} already done, {len(todo)} to run")

    results = []
    for number, url in enumerate(todo, start=1):
        if number > 1 and args.delay > 0:
            time.sleep(args.delay)
        print(f"\n{number} of {len(todo)}")
        results.append(run_one(enrich, url, rows, args.job_urls.get(url_key(url))))
        if args.csv:
            # Written after every company so a stopped run keeps its progress for --resume.
            write_csv(args.csv, rows, announce=False)
    failed = results.count(False)
    print(f"\n{len(results) - failed} of {len(results)} URLs enriched")
    if args.csv:
        write_csv(args.csv, rows)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
