import enrich
from enrich import Company

SITE = {
    "name": "Stripe",
    "title": "Stripe | Payments",
    "description": "Online payment processing for internet businesses.",
    "about_url": "https://stripe.com/about",
    "about": "Millions of companies use Stripe to accept payments.",
    "error": None,
}
COMPANY = Company(
    industry="Fintech",
    what_they_sell="Payment processing APIs",
    target_customer="Online businesses",
)


def test_enrich_returns_company_from_mocked_scraper_and_llm(monkeypatch):
    prompts = []

    def fake_ask(prompt):
        prompts.append(prompt)
        return COMPANY, "fake-model"

    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    monkeypatch.setattr(enrich, "ask", fake_ask)

    out = enrich.enrich("stripe.com")

    assert out == {"name": "Stripe", "company": COMPANY, "model": "fake-model", "error": None}
    assert "Online payment processing" in prompts[0]
    assert "Millions of companies" in prompts[0]


def test_enrich_passes_scraper_error_through_without_calling_llm(monkeypatch):
    def fail_if_called(prompt):
        raise AssertionError("ask() must not be called when the scrape failed")

    site = {**SITE, "description": None, "about": None, "error": "Could not reach site"}
    monkeypatch.setattr(enrich, "get_description", lambda url: site)
    monkeypatch.setattr(enrich, "ask", fail_if_called)

    out = enrich.enrich("stripe.com")

    assert out["error"] == "Could not reach site"
    assert out["company"] is None


def test_enrich_errors_when_site_has_no_description_or_about(monkeypatch):
    site = {**SITE, "description": None, "about": None}
    monkeypatch.setattr(enrich, "get_description", lambda url: site)
    monkeypatch.setattr(enrich, "ask", lambda prompt: (COMPANY, "fake-model"))

    out = enrich.enrich("stripe.com")

    assert out["error"] == "No description could be found"
    assert out["company"] is None


def test_enrich_errors_when_all_models_are_busy(monkeypatch):
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    monkeypatch.setattr(enrich, "ask", lambda prompt: (None, None))

    out = enrich.enrich("stripe.com")

    assert "busy" in out["error"]
    assert out["company"] is None


def test_ask_falls_through_to_next_provider(monkeypatch):
    monkeypatch.setattr(enrich, "PROVIDERS", [lambda p: (None, None), lambda p: (COMPANY, "groq-model")])

    assert enrich.ask("prompt") == (COMPANY, "groq-model")


def test_ask_returns_none_when_every_provider_fails(monkeypatch):
    monkeypatch.setattr(enrich, "PROVIDERS", [lambda p: (None, None), lambda p: (None, None)])

    assert enrich.ask("prompt") == (None, None)
