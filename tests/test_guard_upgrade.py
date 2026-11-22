"""T3 guard upgrade: dash and acronym fixes, fact sheets, and the demo claim check.

Every note and company here is SYNTHETIC.
"""

import csv
from pathlib import Path

import pytest

import enrich
import facts
import pitch

FIXTURES = Path(__file__).parent / "fixtures"

# Synthetic site. It deliberately contains none of NAV, ACID, CFO, Chief, Officer, Ops or Manager.
SITE = {
    "name": "Echobench",
    "url": "https://echobench.example",
    "title": "Echobench | Testing and monitoring for voice AI agents",
    "description": "Echobench tests and monitors voice AI agents with simulated callers before and after go live.",
    "about": "Echobench helps teams find failing turns in voice agent scripts.",
    "error": None,
}

LOOM_LINE = "Loom: [LOOM_URL] Repo: [REPO_URL]"


def note_with(opening):
    return (
        f"{opening}\n\nFirst, the site says Echobench tests voice AI agents with simulated callers.\n"
        f"Second, I would adapt the personas to your clients.\n\n{LOOM_LINE}"
    )


def make_company(cluster, note):
    return enrich.Company(
        industry="x",
        what_they_sell="x",
        target_customer="x",
        cluster=cluster,
        cluster_reason="x",
        customer_pain="x",
        tailoring=["a", "b", "c"],
        pitch_note=note,
    )


def violations_for(note, cluster="A"):
    return enrich.guard_violations(make_company(cluster, note), SITE)


def test_u2011_dash_is_normalised_not_rejected():
    dirty = note_with("I built a voice agent call QA demo, a three" + chr(0x2011) + "way check" + chr(0x2013) + "for you.")

    cleaned = enrich.clean_note(make_company("A", dirty))

    assert not any(char in cleaned.pitch_note for char in pitch.DASH_CHARACTERS)
    assert enrich.guard_violations(cleaned, SITE) == []
    # The backstop still rejects a dash that skipped the cleaner.
    assert any("hyphen or dash" in line for line in pitch.check_pitch_note(dirty))


def test_nfkc_turns_compatibility_dashes_into_spaces():
    assert pitch.normalise_dashes("three" + chr(0xFF0D) + "way" + chr(0xFE63) + "match") == "three way match"


def test_nfkc_is_applied_to_evidence_quotes_before_matching():
    site = {**SITE, "description": "Echobench tests voice AI agents with simulated callers."}
    fullwidth = chr(0xFF25) + "chobench tests voice AI agents with simulated callers"

    assert pitch.check_evidence([fullwidth], site) == []


def test_nav_acid_cfo_pass_as_acronyms():
    note = note_with("I built a voice agent call QA demo, so your CFO can check NAV and ACID style scripts.")

    assert violations_for(note) == []


def test_chief_officer_ops_manager_not_flagged():
    note = note_with("I built a voice agent call QA demo for a Chief Officer or an Ops Manager.")

    assert violations_for(note) == []


@pytest.mark.parametrize(
    "invented",
    [
        "Zorvex Labs",
        "Quillbridge",
        "NovaLedger",
        "Pelagic AI",
        "Marrow Inc",
        "Fennel Ops",
        "Kestrel Manager",
        "Chief Zorvex",
        "Brightloop",
        "Tessellate Labs",
    ],
)
def test_invented_company_still_flagged(invented):
    note = note_with(f"I built a voice agent call QA demo, in the same space as {invented}.")

    found = violations_for(note)

    assert any("names not found on the site" in line for line in found), found


def test_invented_name_next_to_a_title_word_is_flagged_and_the_title_word_is_not():
    note = note_with("I built a voice agent call QA demo for the Chief Officer at Zorvex.")

    found = [line for line in violations_for(note) if "names not found" in line]

    assert len(found) == 1
    assert "Zorvex" in found[0]
    assert "Chief" not in found[0] and "Officer" not in found[0]


def test_sub_100ms_latency_rejected_for_call_qa():
    note = note_with("I built a voice agent call QA demo that proves sub 100ms latency.")

    found = violations_for(note)

    assert any("latency" in line and "call-qa.md" in line for line in found), found
    assert any("100ms" in line and "call-qa.md" in line for line in found), found


def test_claim_in_fact_sheet_passes():
    note = note_with(
        "I built a voice agent call QA demo that runs about 20 simulated callers, "
        "including Hinglish and adversarial callers."
    )

    assert violations_for(note) == []


def test_unit_number_in_the_numbers_list_is_allowed():
    sheet = {**facts.load("call-qa"), "numbers": ["99% pass rate after the prompt fix"]}

    assert pitch.check_demo_claims("I built a demo with a 99% pass rate after the prompt fix.", sheet) == []
    assert pitch.check_demo_claims("I built a demo with a 98% pass rate.", sheet)


def test_sentence_about_the_company_own_product_is_not_checked():
    note = "Echobench tests voice AI agents and talks about latency and uptime.\n\n" + LOOM_LINE

    assert pitch.check_demo_claims(note, facts.load("call-qa")) == []


def test_invoice_triage_sheet_rejects_bank_reconciliation_claim():
    sheet = facts.load("invoice-exception-triage")

    found = pitch.check_demo_claims("I built an invoice exception triage demo that does bank reconciliation.", sheet)

    assert found
    assert "bank reconciliation" in found[0]
    assert "invoice-exception-triage.md" in found[0]


def test_fact_sheet_matches_what_enrich_uses():
    call_qa = facts.load("call-qa")
    triage = facts.load("invoice-exception-triage")

    assert enrich.DEMO_FACTS_A == facts.prompt_text(call_qa, "A")
    assert enrich.DEMO_FACTS_B == facts.prompt_text(triage, "B")
    prompt = enrich.build_prompt({**SITE, "about": None})
    assert enrich.DEMO_FACTS_A in prompt
    assert enrich.DEMO_FACTS_B in prompt
    for bullet in call_qa["does"] + triage["does"]:
        assert bullet in prompt
    # The one added prompt line names what the demos do not measure.
    assert "latency" in prompt and "bank reconciliation" in prompt


def test_fact_sheets_have_the_required_sections():
    for name in ("call-qa", "invoice-exception-triage"):
        sheet = facts.load(name)
        assert sheet["repo"]
        assert sheet["does"] and sheet["not_measured"] and sheet["numbers"]
    assert {"latency", "response time", "uptime"} <= set(facts.load("call-qa")["not_measured"])
    assert {"bank reconciliation", "fraud"} <= set(facts.load("invoice-exception-triage")["not_measured"])


def read_synthetic_notes():
    with (FIXTURES / "synthetic_notes.csv").open(newline="") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    rows = list(csv.DictReader(lines))
    for row in rows:
        row["note"] = row["note"].replace("\\u2011", chr(0x2011))
    return rows


def test_synthetic_notes_fixture_is_labelled_and_has_six_rows():
    first_line = (FIXTURES / "synthetic_notes.csv").read_text().splitlines()[0]

    assert first_line.startswith("#") and "SYNTHETIC" in first_line
    assert len(read_synthetic_notes()) == 6


def test_synthetic_good_notes_still_pass():
    for row in read_synthetic_notes():
        company = enrich.clean_note(make_company(row["cluster"], row["note"]))
        found = enrich.guard_violations(company, SITE)
        if row["expect"] == "pass":
            assert found == [], (row["id"], found)
        else:
            assert found, row["id"]


# Paraphrases of a latency claim. The check is phrase matching, so some slip through. The test pins
# the measured miss rate: if the check changes, this number must be updated on purpose.
PARAPHRASES = [
    "I built a call QA demo that answers under a tenth of a second.",
    "I built a call QA demo that checks how snappy the agent feels.",
    "I built a call QA demo that measures how quickly the agent replies.",
    "I built a call QA demo that proves a 250 ms pause.",
    "I built a call QA demo that checks the delay before the agent speaks.",
]


def test_paraphrase_miss_rate_is_known():
    sheet = facts.load("call-qa")

    missed = [text for text in PARAPHRASES if not pitch.check_demo_claims(text, sheet)]

    assert len(missed) == 4, missed
