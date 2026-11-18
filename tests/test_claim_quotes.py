import pytest

import enrich
import pitch
from tests.test_pitch_engine import AP_NOTE, AP_SITE, make_company, script_ask, use_site

# Every site and note here is SYNTHETIC. The companies are fictional.

GOOD_QUOTE = "Ledgerly automates accounts payable for finance teams"
SITE_WITH_JOB = {
    **AP_SITE,
    "customers": "Customers include Zephyrbank and Northwind Traders.",
    "job_title": "Forward Deployed Engineer",
    "job_post": "You will deploy invoice agents inside customer finance teams.",
}
# A sentence about the company that claims a result, with no words from any quote.
CLAIM = "Ledgerly cuts invoice errors by half for its customers."
LOOM_LINE = "Loom: [LOOM_URL] Repo: [REPO_URL]"


def note_with(sentence):
    return AP_NOTE.replace(LOOM_LINE, sentence + "\n\n" + LOOM_LINE)


@pytest.fixture(autouse=True)
def evidence_required(monkeypatch):
    monkeypatch.setattr(enrich, "REQUIRE_EVIDENCE", True)


# ---------- pure checks in pitch.py ----------


def test_normalise_quote_ignores_case_punctuation_dashes_and_curly_marks():
    a = pitch.normalise_quote("Ledgerly’s  “three-way” match, fast!")
    b = pitch.normalise_quote("ledgerly's three way match fast")

    assert a == b


def test_a_verbatim_quote_passes_even_with_different_case_and_spacing():
    assert pitch.check_evidence(["ledgerly  AUTOMATES accounts payable, for finance teams"], AP_SITE) == []


def test_a_quote_the_site_never_said_is_rejected():
    violations = pitch.check_evidence(["Ledgerly halves invoice errors for every customer"], AP_SITE)

    assert len(violations) == 1
    assert "not found on the site" in violations[0]
    assert "halves invoice errors" in violations[0]


def test_a_quote_of_fewer_than_three_words_proves_nothing():
    violations = pitch.check_evidence(["accounts payable"], AP_SITE)

    assert len(violations) == 1
    assert "too short" in violations[0]


@pytest.mark.parametrize("evidence", [[], ["", "   "]])
def test_no_quotes_at_all_is_a_violation(evidence):
    violations = pitch.check_evidence(evidence, AP_SITE)

    assert len(violations) == 1
    assert "no quotes" in violations[0]


def test_a_quote_may_come_from_the_customers_text_or_the_job_post():
    assert pitch.check_evidence(["include Zephyrbank and Northwind Traders"], SITE_WITH_JOB) == []
    assert pitch.check_evidence(["deploy invoice agents inside customer finance teams"], SITE_WITH_JOB) == []


def test_the_demo_fact_sheet_is_not_a_source_for_quotes():
    site = {**AP_SITE, "demo_facts": "The demo flags every duplicate invoice in three messy exports"}

    violations = pitch.check_evidence(["flags every duplicate invoice in three messy exports"], site)

    assert len(violations) == 1


def test_a_company_name_alone_does_not_make_a_quote_real():
    # The name and the host are in the guard corpus but are not site sentences.
    violations = pitch.check_evidence(["ledgerly example cuts errors"], AP_SITE)

    assert len(violations) == 1


def test_an_outcome_claim_with_no_matching_quote_is_flagged():
    violations = pitch.check_outcome_claims(note_with(CLAIM), [GOOD_QUOTE])

    assert len(violations) == 1
    assert "no quote" in violations[0]
    assert "cuts invoice errors by half" in violations[0]


def test_an_outcome_claim_backed_by_a_quote_passes():
    site = {**AP_SITE, "description": AP_SITE["description"] + " Ledgerly cuts invoice errors by half."}
    quote = "Ledgerly cuts invoice errors by half"

    assert pitch.check_evidence([quote], site) == []
    assert pitch.check_outcome_claims(note_with(CLAIM), [quote]) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "First, I would reduce the manual matching in the sample data.",
        "I would cut the demo to three exports.",
        "Second, we would improve the personas.",
        "The demo reads Tally and Zoho exports.",
    ],
)
def test_sentences_by_the_author_or_with_no_outcome_word_are_not_claims(sentence):
    assert pitch.check_outcome_claims(note_with(sentence), [GOOD_QUOTE]) == []


def test_the_loom_line_is_never_a_claim():
    note = "Ledgerly is a fit.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]"

    assert pitch.check_outcome_claims(note, [GOOD_QUOTE]) == []


def test_pitch_violations_skips_the_evidence_checks_when_no_evidence_is_given():
    assert pitch.pitch_violations(note_with(CLAIM), AP_SITE) == pitch.pitch_violations(note_with(CLAIM), AP_SITE, evidence=None)
    assert not any("quote" in v for v in pitch.pitch_violations(note_with(CLAIM), AP_SITE))


def test_pitch_violations_adds_both_evidence_checks_when_evidence_is_given():
    violations = pitch.pitch_violations(note_with(CLAIM), AP_SITE, evidence=["Ledgerly is the best invoice tool ever made"])

    assert any("not found on the site" in v for v in violations)
    assert any("no quote" in v for v in violations)


# ---------- the enrich flow ----------


def test_the_company_answer_has_an_evidence_list_and_the_prompt_asks_for_quotes():
    assert "evidence" in enrich.Company.model_fields
    prompt = enrich.build_prompt(AP_SITE)

    assert "evidence" in prompt
    assert "copied exactly" in prompt
    assert "at least 3 words" in prompt


def test_a_grounded_note_with_real_quotes_is_accepted_and_returns_its_evidence(monkeypatch):
    use_site(monkeypatch, AP_SITE)
    prompts = script_ask(monkeypatch, [(make_company("B", AP_NOTE, evidence=[GOOD_QUOTE]), "m1")])

    out = enrich.enrich("ledgerly.example")

    assert len(prompts) == 1
    assert out["pitch_note"] == AP_NOTE
    assert out["pitch_error"] is None
    assert out["evidence"] == [GOOD_QUOTE]


def test_a_made_up_quote_triggers_one_retry_that_names_the_problem(monkeypatch):
    use_site(monkeypatch, AP_SITE)
    fake = make_company("B", AP_NOTE, evidence=["Ledgerly is trusted by every bank in India"])
    real = make_company("B", AP_NOTE, evidence=[GOOD_QUOTE])
    prompts = script_ask(monkeypatch, [(fake, "m1"), (real, "m2")])

    out = enrich.enrich("ledgerly.example")

    assert len(prompts) == 2
    assert "evidence quote not found on the site" in prompts[1]
    assert out["evidence"] == [GOOD_QUOTE]
    assert out["model"] == "m2"


def test_an_unquoted_outcome_claim_is_dropped_after_two_failures(monkeypatch):
    use_site(monkeypatch, AP_SITE)
    bad = make_company("B", note_with(CLAIM), evidence=[GOOD_QUOTE])
    prompts = script_ask(monkeypatch, [(bad, "m1"), (bad, "m2")])

    out = enrich.enrich("ledgerly.example")

    assert len(prompts) == 2
    assert out["pitch_note"] is None
    assert "no quote" in out["pitch_error"]
    assert out["error"] is None


def test_an_answer_with_no_quotes_is_retried(monkeypatch):
    use_site(monkeypatch, AP_SITE)
    prompts = script_ask(
        monkeypatch,
        [(make_company("B", AP_NOTE, evidence=[]), "m1"), (make_company("B", AP_NOTE, evidence=[GOOD_QUOTE]), "m2")],
    )

    out = enrich.enrich("ledgerly.example")

    assert len(prompts) == 2
    assert "no quotes" in prompts[1]
    assert out["evidence"] == [GOOD_QUOTE]


def test_evidence_is_not_enforced_when_the_switch_is_off(monkeypatch):
    monkeypatch.setattr(enrich, "REQUIRE_EVIDENCE", False)
    use_site(monkeypatch, AP_SITE)
    prompts = script_ask(monkeypatch, [(make_company("B", AP_NOTE, evidence=[]), "m1")])

    out = enrich.enrich("ledgerly.example")

    assert len(prompts) == 1
    assert out["pitch_note"] == AP_NOTE


def test_the_switch_is_on_in_the_shipped_code():
    import re
    from pathlib import Path

    source = Path(enrich.__file__).read_text(encoding="utf-8")

    assert re.search(r"^REQUIRE_EVIDENCE=True$", source, re.MULTILINE)
