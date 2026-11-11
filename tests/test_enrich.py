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


def make_company(industry="Fintech", what_they_sell="Payment APIs", target_customer="Online businesses"):
    return Company(industry=industry, what_they_sell=what_they_sell, target_customer=target_customer)


def enrich_with_answer(monkeypatch, company):
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    monkeypatch.setattr(enrich, "ask", lambda prompt: (company, "fake-model"))
    return enrich.enrich("stripe.com")


def test_enrich_errors_when_all_fields_are_not_available(monkeypatch):
    junk = make_company("Not available", "Not available", "Not available")

    out = enrich_with_answer(monkeypatch, junk)

    assert out["company"] is None
    assert out["model"] is None
    assert out["name"] == "Stripe"
    assert out["error"] == (
        "The model could not fill in industry, what_they_sell, target_customer from the site text "
        "(it answered 'Not available'). The site gave too little to go on, please check the site manually."
    )


def test_enrich_error_names_only_the_junk_field(monkeypatch):
    out = enrich_with_answer(monkeypatch, make_company(target_customer="Not available"))

    assert out["company"] is None
    assert "target_customer" in out["error"]
    assert "industry" not in out["error"]
    assert "what_they_sell" not in out["error"]


def test_enrich_treats_junk_variants_as_missing(monkeypatch):
    variants = ["N/A", "unknown", "UNKNOWN", "  not available.  ", "None", "Not specified", "No information found"]
    for value in variants:
        out = enrich_with_answer(monkeypatch, make_company(industry=value))
        assert out["company"] is None, value
        assert "industry" in out["error"], value


def test_enrich_keeps_real_values_that_only_contain_junk_words(monkeypatch):
    company = make_company(industry="Nanotechnology", what_they_sell="Nonprofit accounting software")
    company.target_customer = "Nathan's bakery chain"

    out = enrich_with_answer(monkeypatch, company)

    assert out["error"] is None
    assert out["company"] is company


def test_prompt_leaves_out_missing_description(monkeypatch):
    prompts = []
    site = {**SITE, "description": None}
    monkeypatch.setattr(enrich, "get_description", lambda url: site)
    monkeypatch.setattr(enrich, "ask", lambda prompt: prompts.append(prompt) or (COMPANY, "fake-model"))

    enrich.enrich("stripe.com")

    assert "Not available" not in prompts[0]
    assert "Description:" not in prompts[0]
    assert "About page: Millions of companies" in prompts[0]
    assert "UNKNOWN" in prompts[0]


def test_prompt_leaves_out_missing_about_and_keeps_description(monkeypatch):
    prompts = []
    site = {**SITE, "about": None}
    monkeypatch.setattr(enrich, "get_description", lambda url: site)
    monkeypatch.setattr(enrich, "ask", lambda prompt: prompts.append(prompt) or (COMPANY, "fake-model"))

    enrich.enrich("stripe.com")

    assert "Not available" not in prompts[0]
    assert "About page:" not in prompts[0]
    assert "Description: Online payment processing" in prompts[0]
