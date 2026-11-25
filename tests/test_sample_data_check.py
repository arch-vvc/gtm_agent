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
