"""Run the pitch engine on real URLs, with real model calls, and print what comes back.

Usage from the repo root:

    python -m scripts.real_run [--provider gemini|groq|all] URL [URL ...]

This calls enrich.enrich(url) directly. Nothing is written to Postgres and no job
is queued. For every URL it prints the full result as JSON, then the pitch markdown
the API would serve, and a WARNING line when the grounding guard left pitch_note empty.

It needs GEMINI_API_KEY and GROQ_API_KEY in the environment. The Gemini path also
uses Redis for its model cooldowns, so run this inside the worker container, which
has the keys and a Redis next to it:

    docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run peakflo.co cekura.ai

Outside Docker, point REDIS_HOST at a Redis you can reach. The exit code is non zero
when any URL ended with an error.
"""

import argparse
import json
import sys

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


def run_one(enrich, url):
    """Enrich one URL and print everything. Returns True when it worked."""
    print(f"\n===== {url} =====")
    out = enrich.enrich(url)

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

    results = [run_one(enrich, url) for url in args.urls]
    failed = results.count(False)
    print(f"\n{len(results) - failed} of {len(results)} URLs enriched")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
