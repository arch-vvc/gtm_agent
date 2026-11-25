"""Tailoring may not suggest sample data or scripts taken from a named company. All names here are SYNTHETIC.

Sample data is synthetic and labelled. A tailoring item that says "data from Acme" or "Acme's invoice data" would
have the demo use someone else's real data, so the guard rejects it and the engine retries.
"""

import pytest

import enrich
import pitch
from tests.test_pitch_engine import make_company

BAD_ITEMS = [
    "Use invoice data from Ninja Van",
    "Build sample scripts from Carousell support calls",
    "Mirror Ninja Van's invoice data in the demo",
    "Replay transcripts of Acme Logistics as the sample calls",
    "Use Carousell’s call logs as sample data",
]
GOOD_ITEMS = [
    "Use Tally style sample data",
    "Generate synthetic invoices with Indian number formats",
    "Name personas after AP clerks",
    "Take sample data from Tally and Zoho exports",
    "Say GST not VAT",
]


@pytest.mark.parametrize("item", BAD_ITEMS)
def test_named_company_data_source_is_flagged(item):
    assert pitch.check_tailoring_sources([item]), item


@pytest.mark.parametrize("item", GOOD_ITEMS)
def test_generic_sources_pass(item):
    assert pitch.check_tailoring_sources([item]) == [], item


def test_guard_violations_includes_the_check_even_when_the_name_is_on_the_site():
    company = make_company("B", "x", tailoring=["Use invoice data from Ninja Van", "Name personas after AP clerks", "Say GST not VAT"])
    site = {"name": "Peakflo", "title": "Peakflo", "description": "Customers include Ninja Van.", "about": "Ninja Van uses us."}
    violations = enrich.guard_violations(company, site)
    assert any("tailoring" in v and "Ninja Van" in v for v in violations), violations


LABELLED_ITEMS = [
    "Sample data: Use invoice, purchase order, and payment exports from multi-entity enterprise accounts.",
    "Persona names: Set up role-based views for accounts payable managers.",
    "Terminology: Label exception categories using 2-way and 3-way match errors.",
]
SITE_WITHOUT_THOSE_WORDS = {"name": "Peakflo", "title": "Peakflo", "description": "Accounts payable automation with 2-way and 3-way matching.", "about": "Finance teams."}


@pytest.mark.parametrize("item", LABELLED_ITEMS)
def test_a_label_then_a_verb_is_not_read_as_a_company_name(item):
    company = make_company("B", "x", tailoring=[item, "Name personas after AP clerks", "Say GST not VAT"])
    violations = enrich.guard_violations(company, SITE_WITHOUT_THOSE_WORDS)
    assert not [v for v in violations if "in tailoring" in v], violations


def test_a_real_invented_name_after_a_label_is_still_caught():
    company = make_company("B", "x", tailoring=["Sample data: Mirror Zorbex exports", "Name personas after AP clerks", "Say GST not VAT"])
    violations = enrich.guard_violations(company, SITE_WITHOUT_THOSE_WORDS)
    assert any("in tailoring" in v and "Zorbex" in v for v in violations), violations
