"""Guard holes found in review: notes that passed every check but should not have.

Every site and note here is SYNTHETIC. The companies are fictional.
"""

from types import SimpleNamespace

import pytest

import enrich
import pitch

QUOTE = "helps support teams answer calls"
SITE = {
    "name": "Callwell",
    "url": "https://callwell.example",
    "title": "Callwell",
    "description": "Callwell helps support teams answer calls.",
    "about": "Customers include Foo Bank and Northwind Telecom.",
}
BUILT_LINE = "Loom: [LOOM_URL] Repo: [REPO_URL]"
NOT_BUILT_LINE = "Repo: [REPO_URL]"


def note_with(sentence, last_line=BUILT_LINE):
    return f"I built a call QA demo for Callwell customers.\n\n{sentence}\n\n{last_line}"


# ---------- an author sentence that puts a size on a result is still a claim ----------


@pytest.mark.parametrize(
    "sentence",
    [
        "First, I would show how it cuts your churn in half and saves millions.",
        "Second, we would reduce handling time by 40%.",
        "I would make reviews 3x faster for Foo Bank.",
    ],
)
def test_an_author_sentence_with_a_size_on_the_result_needs_a_quote(sentence):
    violations = pitch.check_outcome_claims(note_with(sentence), [QUOTE])

    assert len(violations) == 1
    assert "no quote" in violations[0]


def test_an_author_sentence_without_a_size_is_still_not_a_claim():
    sentence = "First, I would reduce the manual review in the sample calls."

    assert pitch.check_outcome_claims(note_with(sentence), [QUOTE]) == []


# ---------- "we" claims of work not done are caught like "I" claims ----------


@pytest.mark.parametrize(
    "sentence",
    ["We adapted it to your stack.", "First, we've integrated it.", "we have also configured the personas."],
)
def test_we_claims_of_work_not_done_are_flagged(sentence):
    violations = pitch.check_pitch_claims(sentence)

    assert len(violations) == 1
    assert "(write 'I would" in violations[0]


def test_we_would_is_still_allowed():
    assert pitch.check_pitch_claims("Second, we would adapt the personas.") == []


def test_we_built_does_not_count_as_the_author_claiming_a_built_demo():
    assert not pitch.claims_built_demo("we built it")


# ---------- the demo described as already working on the company's own material ----------


def test_the_demo_said_to_load_a_name_not_in_its_facts_is_flagged():
    site = {**SITE, "demo_facts": enrich.DEMO_FACTS_A}
    note = note_with("First, the demo loads real Northwind Telecom billing scripts.")

    violations = pitch.check_demo_claims(note, site)

    assert len(violations) == 1
    assert "Northwind" in violations[0]
    assert "I would adapt" in violations[0]


@pytest.mark.parametrize(
    "sentence, facts",
    [
        ("The demo runs about 20 simulated callers, including Hinglish ones.", enrich.DEMO_FACTS_A),
        ("The demo reads Tally and Zoho exports.", enrich.DEMO_FACTS_B),
        ("I would adapt the demo to load Northwind Telecom scripts.", enrich.DEMO_FACTS_A),
    ],
)
def test_the_demo_described_with_its_own_facts_or_in_the_future_passes(sentence, facts):
    site = {**SITE, "demo_facts": facts}

    assert pitch.check_demo_claims(note_with(sentence), site) == []


def test_demo_claims_are_not_checked_without_demo_facts():
    note = note_with("First, the demo loads real Northwind Telecom billing scripts.")

    assert pitch.check_demo_claims(note, SITE) == []


def test_pitch_violations_include_the_demo_claims():
    site = {**SITE, "demo_facts": enrich.DEMO_FACTS_A}
    note = note_with("First, the demo loads real Northwind Telecom billing scripts.")

    assert any("Northwind" in violation for violation in pitch.pitch_violations(note, site))


# ---------- no Loom line for a cluster with no demo built ----------


def test_a_note_with_no_demo_built_must_not_carry_the_loom_line():
    violations = pitch.check_pitch_note(note_with("First, I would build a quote checker.", BUILT_LINE), built=False)

    assert violations == [f"last line must be exactly: {NOT_BUILT_LINE} (no demo is built, so no Loom)"]


def test_a_note_with_no_demo_built_ends_with_the_repo_line_only():
    note = note_with("First, I would build a quote checker.", NOT_BUILT_LINE)

    assert pitch.check_pitch_note(note, built=False) == []
    assert pitch.check_pitch_note(note) == [f"last line must contain {pitch.LOOM} and end with {pitch.REPO}"]


def test_the_guard_rejects_a_loom_line_for_a_cluster_with_no_demo(monkeypatch):
    monkeypatch.setattr(enrich, "REQUIRE_EVIDENCE", False)
    company = SimpleNamespace(cluster="D", pitch_note=note_with("First, I would build a quote checker.", BUILT_LINE))

    assert any("no Loom" in violation for violation in enrich.guard_violations(company, SITE))


def test_the_guard_accepts_the_loom_line_for_a_built_cluster(monkeypatch):
    monkeypatch.setattr(enrich, "REQUIRE_EVIDENCE", False)
    company = SimpleNamespace(cluster="A", pitch_note=note_with("First, I would adapt the personas.", BUILT_LINE))

    assert not any("Loom" in violation for violation in enrich.guard_violations(company, SITE))


def test_the_prompt_gives_both_last_lines():
    prompt = enrich.build_prompt(SITE)

    assert prompt.endswith(f"Loom: {pitch.LOOM} Repo: {pitch.REPO}")
    assert f"Keep the structure, ending with {NOT_BUILT_LINE} alone." in prompt
