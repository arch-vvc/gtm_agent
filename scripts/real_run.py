"""Run the pitch engine on real URLs, with real model calls, and print what comes back.

Usage from the repo root:

    python -m scripts.real_run [--provider gemini|groq|all] [--csv PATH] URL [URL ...]

This calls enrich.enrich(url) directly. Nothing is written to Postgres and no job
is queued. With --csv PATH it also writes one row per URL (errors included) to a CSV
file. For every URL it prints the full result as JSON, then the pitch markdown
the API would serve, and a WARNING line when the grounding guard left pitch_note empty.

It needs GEMINI_API_KEY and GROQ_API_KEY in the environment. The Gemini path also
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
import sys
from pathlib import Path

import pitch


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
        help="also write one row per URL, errors included, to this CSV file (parent folders are created)",
    )
    parser.add_argument("urls", metavar="URL", nargs="+", help="company website, for example peakflo.co")
    return parser.parse_args(argv)


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
]


def cell(value):
    """One CSV cell: None is empty, booleans are true or false, everything else is text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
        )
        if company:
            row.update(
                cluster=company.cluster,
                cluster_reason=company.cluster_reason,
                customer_pain=company.customer_pain,
                tailoring=" | ".join(company.tailoring),
            )
    return [cell(row.get(column)) for column in CSV_COLUMNS]


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)
    print(f"\nCSV written to {path} ({len(rows)} rows)")


def run_one(enrich, url, rows):
    """Enrich one URL, print everything and add its CSV row to rows. Returns True when it worked."""
    print(f"\n===== {url} =====")
    try:
        out = enrich.enrich(url)
    except Exception as exc:  # noqa: BLE001
        # Blind except on purpose: one bad URL must not stop the run.
        # Only the class and the message are printed, never keys or environment values.
        print(f"ERROR: {type(exc).__name__}: {exc}")
        rows.append(csv_row(url, error=f"{type(exc).__name__}: {exc}"))
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


def main(argv=None):
    args = parse_args(argv)

    # Imported here because importing enrich builds the Gemini and Groq clients,
    # which need API keys. --help must work without them.
    import enrich

    enrich.PROVIDERS = choose_providers(enrich, args.provider)

    rows = []
    results = [run_one(enrich, url, rows) for url in args.urls]
    failed = results.count(False)
    print(f"\n{len(results) - failed} of {len(results)} URLs enriched")
    if args.csv:
        write_csv(args.csv, rows)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
