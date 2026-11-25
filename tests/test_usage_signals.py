"""T4a: tokens, cost estimate, latency and prompt version per enrich() call.

The fake responses use the real SDK classes, so the field names pinned here are the ones the
installed SDKs define: Gemini GenerateContentResponseUsageMetadata (prompt_token_count,
candidates_token_count, thoughts_token_count) and Groq CompletionUsage (prompt_tokens,
completion_tokens). No network and no keys.
"""

import csv
import hashlib
import time
from types import SimpleNamespace

import pytest
from google.genai import types
from groq.types import CompletionUsage

import enrich
import pricing
from scripts import real_run
from tests.test_enrich import COMPANY, SITE

GROQ_SMALL = "openai/gpt-oss-20b"


class FakeRedis:
    def exists(self, key):
        return False

    def set(self, key, value, ex=None):
        pass


def gemini_response(prompt_tokens, candidate_tokens, thought_tokens=None):
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt_tokens,
        candidates_token_count=candidate_tokens,
        thoughts_token_count=thought_tokens,
    )
    return SimpleNamespace(parsed=COMPANY, usage_metadata=usage)


def groq_response(prompt_tokens, completion_tokens):
    usage = CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    message = SimpleNamespace(content=COMPANY.model_dump_json())
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def run_enrich(monkeypatch, ask):
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    monkeypatch.setattr(enrich, "ask", ask)
    return enrich.enrich("stripe.com")


def test_gemini_usage_metadata_is_summed(monkeypatch):
    responses = iter([gemini_response(1000, 200, thought_tokens=50)])
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: next(responses)))
    monkeypatch.setattr(enrich, "r", FakeRedis())
    monkeypatch.setattr(enrich, "gemini_client", client)
    monkeypatch.setattr(enrich, "PROVIDERS", [enrich.ask_gemini])

    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    out = enrich.enrich("stripe.com")

    assert out["usage"]["input_tokens"] == 1000
    # Thinking tokens are billed as output, so they are counted with the candidate tokens.
    assert out["usage"]["output_tokens"] == 250
    assert out["model"] == enrich.GEMINI_MODELS[0]


def test_groq_usage_is_summed(monkeypatch):
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: groq_response(800, 120)))
    )
    monkeypatch.setattr(enrich, "groq_client", client)
    monkeypatch.setattr(enrich, "PROVIDERS", [enrich.ask_groq])
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)

    out = enrich.enrich("stripe.com")

    assert out["usage"]["input_tokens"] == 800
    assert out["usage"]["output_tokens"] == 120
    assert out["model"] == GROQ_SMALL
    expected = (800 * 0.075 + 120 * 0.30) / 1_000_000
    assert out["usage"]["cost_usd_est"] == pytest.approx(expected)


def test_retry_tokens_are_added(monkeypatch):
    answers = iter([(100, 10), (300, 30)])

    def fake_ask(prompt):
        tokens_in, tokens_out = next(answers)
        enrich.record_usage(GROQ_SMALL, tokens_in, tokens_out)
        return COMPANY, GROQ_SMALL

    verdicts = iter([["a made up claim"], []])
    monkeypatch.setattr(enrich, "guard_violations", lambda company, site: next(verdicts))

    out = run_enrich(monkeypatch, fake_ask)

    assert out["usage"]["input_tokens"] == 400
    assert out["usage"]["output_tokens"] == 40
    assert len(out["usage"]["calls"]) == 2


def test_unknown_model_cost_is_blank_not_zero(monkeypatch):
    def fake_ask(prompt):
        enrich.record_usage("some-model-not-in-the-table", 100, 10)
        return COMPANY, "some-model-not-in-the-table"

    out = run_enrich(monkeypatch, fake_ask)

    assert out["usage"]["input_tokens"] == 100
    assert out["usage"]["cost_usd_est"] is None
    assert pricing.estimate_cost("some-model-not-in-the-table", 100, 10) is None
    assert pricing.estimate_cost(GROQ_SMALL, 0, 0) == 0


def test_no_calls_means_no_cost(monkeypatch):
    monkeypatch.setattr(enrich, "get_description", lambda url: {**SITE, "error": "Could not reach site"})

    out = enrich.enrich("stripe.com")

    assert out["usage"]["input_tokens"] == 0
    assert out["usage"]["cost_usd_est"] is None


def test_missing_usage_from_the_provider_leaves_tokens_blank(monkeypatch):
    def fake_ask(prompt):
        enrich.record_usage(GROQ_SMALL, None, None)
        return COMPANY, GROQ_SMALL

    out = run_enrich(monkeypatch, fake_ask)

    assert out["usage"]["input_tokens"] is None
    assert out["usage"]["cost_usd_est"] is None


def test_latency_ms_is_wall_time_of_enrich(monkeypatch):
    def slow_ask(prompt):
        time.sleep(0.05)
        return COMPANY, GROQ_SMALL

    out = run_enrich(monkeypatch, slow_ask)

    assert 50 <= out["latency_ms"] < 5000
    assert isinstance(out["latency_ms"], int)


def test_usage_does_not_leak_between_calls(monkeypatch):
    def fake_ask(prompt):
        enrich.record_usage(GROQ_SMALL, 10, 1)
        return COMPANY, GROQ_SMALL

    first = run_enrich(monkeypatch, fake_ask)
    second = run_enrich(monkeypatch, fake_ask)

    assert first["usage"]["input_tokens"] == second["usage"]["input_tokens"] == 10


def test_csv_has_prompt_version_column(tmp_path):
    columns = real_run.CSV_COLUMNS
    tail = ["prompt_version", "input_tokens", "output_tokens", "cost_usd_est", "latency_ms"]
    assert columns[columns.index("evidence") + 1 : columns.index("evidence") + 6] == tail

    out = {
        "name": "Stripe",
        "company": COMPANY,
        "demo": "none built",
        "model": GROQ_SMALL,
        "pitch_note": "n",
        "pitch_error": None,
        "hiring_fde": None,
        "error": None,
        "evidence": [],
        "prompt_version": enrich.PROMPT_VERSION,
        "usage": {"input_tokens": 800, "output_tokens": 120, "cost_usd_est": 0.0000960},
        "latency_ms": 1234,
    }
    path = tmp_path / "run.csv"
    real_run.write_csv(path, [real_run.csv_row("stripe.com", out=out)], announce=False)
    with open(path, encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["prompt_version"] == enrich.PROMPT_VERSION
    assert (row["input_tokens"], row["output_tokens"], row["latency_ms"]) == ("800", "120", "1234")
    assert float(row["cost_usd_est"]) == pytest.approx(0.000096)


def test_csv_leaves_cost_blank_when_unknown():
    out = {
        "name": "x",
        "company": None,
        "demo": None,
        "model": None,
        "pitch_note": None,
        "pitch_error": None,
        "hiring_fde": None,
        "error": "Could not fetch the site",
        "prompt_version": enrich.PROMPT_VERSION,
        "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd_est": None},
        "latency_ms": 90,
    }
    row = dict(zip(real_run.CSV_COLUMNS, real_run.csv_row("x.test", out=out)))

    assert row["cost_usd_est"] == ""
    assert row["latency_ms"] == "90"


# A change to the prompt text has to come with a new PROMPT_VERSION. This pins both: if the
# prompt changes, this test fails until PROMPT_VERSION is bumped and the pair below is updated.
PINNED_PROMPT_VERSION = "pitch-2026-11-25.1"
PINNED_PROMPT_SHA256 = "027494027dc903d94b9a51ba4832a5c292444a1be2183b06e3f37eed813a4523"
FIXED_SITE = {
    "name": "Echobench",
    "title": "Echobench | Voice AI testing",
    "description": "Echobench tests voice AI agents before go live.",
    "about": "We help banks check collections calls.",
    "customers": None,
    "error": None,
}


def test_prompt_version_changes_when_prompt_text_changes():
    digest = hashlib.sha256(enrich.build_prompt(FIXED_SITE).encode("utf-8")).hexdigest()

    assert (enrich.PROMPT_VERSION, digest) == (PINNED_PROMPT_VERSION, PINNED_PROMPT_SHA256), (
        "The prompt text changed. Bump enrich.PROMPT_VERSION to a new dated string and update "
        f"PINNED_PROMPT_VERSION and PINNED_PROMPT_SHA256 here (new hash {digest})."
    )
