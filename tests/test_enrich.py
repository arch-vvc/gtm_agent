import json
from types import SimpleNamespace

import groq
import httpx
import pytest
from google.genai import errors

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
NOTE = "Stripe processes payments for online businesses, so a payments demo fits.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]"
COMPANY = Company(
    industry="Fintech",
    what_they_sell="Payment processing APIs",
    target_customer="Online businesses",
    cluster="F",
    cluster_reason='The site says "accept payments".',
    customer_pain="Online businesses need to accept payments reliably.",
    tailoring=["Use card payment sample data", "Name personas after merchants", "Say payouts not settlements"],
    pitch_note=NOTE,
)


def test_enrich_returns_company_from_mocked_scraper_and_llm(monkeypatch):
    prompts = []

    def fake_ask(prompt):
        prompts.append(prompt)
        return COMPANY, "fake-model"

    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    monkeypatch.setattr(enrich, "ask", fake_ask)

    out = enrich.enrich("stripe.com")

    assert out == {
        "name": "Stripe",
        "company": COMPANY,
        "model": "fake-model",
        "error": None,
        "demo": "none built",
        "pitch_note": NOTE,
        "pitch_error": None,
        "careers_url": None,
        "hiring_fde": None,
        "domain": None,
    }
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
    return COMPANY.model_copy(
        update={"industry": industry, "what_they_sell": what_they_sell, "target_customer": target_customer}
    )


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
        "The model could not fill in industry (answered 'Not available'), "
        "what_they_sell (answered 'Not available'), target_customer (answered 'Not available') from the site text. "
        "The site gave too little to go on, please check the site manually."
    )


def test_enrich_error_quotes_what_the_model_actually_answered(monkeypatch):
    out = enrich_with_answer(monkeypatch, make_company(industry="unknown", target_customer="Not available"))

    assert out["error"] == (
        "The model could not fill in industry (answered 'unknown'), target_customer (answered 'Not available') "
        "from the site text. The site gave too little to go on, please check the site manually."
    )


def test_enrich_error_caps_each_quoted_answer_at_40_characters(monkeypatch):
    long_answer = "Not available " + "x" * 100

    out = enrich_with_answer(monkeypatch, make_company(industry=long_answer))

    assert f"(answered '{long_answer[:40]}')" in out["error"]
    assert long_answer[:41] not in out["error"]


def test_enrich_error_names_only_the_junk_field(monkeypatch):
    out = enrich_with_answer(monkeypatch, make_company(target_customer="Not available"))

    assert out["company"] is None
    assert "target_customer" in out["error"]
    assert "industry" not in out["error"]
    assert "what_they_sell" not in out["error"]


def test_is_junk_handles_quotes_dotted_and_spaced_forms():
    junk = ["\u201cNot available\u201d", "\u2018unknown\u2019", "N.A.", "n / a", "N/A.", "n a", "NA", "n.a. for this site"]
    for value in junk:
        assert enrich.is_junk(value), value


def test_is_junk_treats_empty_whitespace_and_none_as_junk():
    for value in ["", "   ", "\n\t", None, 0]:
        assert enrich.is_junk(value), value


def test_junk_fields_does_not_raise_on_none_values():
    company = make_company()
    company.industry = None

    assert enrich.junk_fields(company) == ["industry"]


def test_is_junk_matches_ambiguous_words_only_as_the_whole_answer():
    for value in ["none", "Unknown", "NA", " None. "]:
        assert enrich.is_junk(value), value
    for value in ["NA region logistics", "None of the above insurance", "Unknown Pleasures records"]:
        assert not enrich.is_junk(value), value


def test_is_junk_matches_unambiguous_placeholders_as_a_prefix():
    for value in ["Not available, see site", "not specified yet", "No information found", "Unavailable (blocked)"]:
        assert enrich.is_junk(value), value


def test_is_junk_keeps_real_answers_that_start_like_a_placeholder():
    for value in ["Nathan's bakeries", "Nanotechnology", "Nonprofit software"]:
        assert not enrich.is_junk(value), value


def test_enrich_keeps_legitimate_answers_that_start_with_ambiguous_words(monkeypatch):
    company = make_company(
        industry="NA region logistics",
        what_they_sell="None of the above insurance",
        target_customer="Unknown Pleasures records",
    )

    out = enrich_with_answer(monkeypatch, company)

    assert out["error"] is None
    assert out["company"] is company


def test_enrich_does_not_try_the_second_provider_when_the_first_gives_a_junk_company(monkeypatch):
    second_calls = []
    junk = make_company("unknown", "unknown", "unknown")
    monkeypatch.setattr(enrich, "PROVIDERS", [lambda p: (junk, "first"), lambda p: second_calls.append(p) or (COMPANY, "second")])
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)

    out = enrich.enrich("stripe.com")

    assert out["company"] is None
    assert "industry" in out["error"]
    assert second_calls == []


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


# Synthetic Loom style example: the home page does not say who buys it, the customers page does.
CUSTOMERS_TEXT = "Product, design and engineering teams\nAtlassian\nHubspot"


def prompt_for(monkeypatch, site):
    prompts = []
    monkeypatch.setattr(enrich, "get_description", lambda url: site)
    monkeypatch.setattr(enrich, "ask", lambda prompt: prompts.append(prompt) or (COMPANY, "fake-model"))
    enrich.enrich("stripe.com")
    return prompts[0]


def test_prompt_includes_customers_page_and_buyer_instruction(monkeypatch):
    site = {**SITE, "customers_url": "https://stripe.com/customers", "customers": CUSTOMERS_TEXT}

    prompt = prompt_for(monkeypatch, site)

    assert f"Customers page: {CUSTOMERS_TEXT}" in prompt
    assert "name the type of buyer, meaning who pays for it" in prompt
    assert "industry, company size or job title" in prompt
    assert "base target_customer on the companies and use cases named there" in prompt
    assert "Mac and PC users" in prompt
    assert "UNKNOWN" in prompt


def test_prompt_omits_customers_section_when_there_is_no_customers_text(monkeypatch):
    for site in [{**SITE, "customers": None}, {**SITE, "customers": ""}, SITE]:
        prompt = prompt_for(monkeypatch, site)

        assert "Customers page:" not in prompt
        assert "name the type of buyer, meaning who pays for it" in prompt
        assert "base target_customer on the companies" not in prompt


def test_prompt_never_asks_for_a_device_or_generic_user_group(monkeypatch):
    prompt = prompt_for(monkeypatch, SITE)

    assert "never answer with a device, operating system or a generic user group" in prompt


def test_enrich_result_carries_the_domain_from_the_scraper(monkeypatch):
    site = {**SITE, "domain": "notion.com"}
    monkeypatch.setattr(enrich, "get_description", lambda url: site)
    monkeypatch.setattr(enrich, "ask", lambda prompt: (COMPANY, "fake-model"))

    out = enrich.enrich("notion.so")

    assert out["domain"] == "notion.com"
    assert out["error"] is None


def test_enrich_result_domain_is_none_when_the_site_dict_has_no_domain(monkeypatch):
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)
    monkeypatch.setattr(enrich, "ask", lambda prompt: (COMPANY, "fake-model"))

    assert enrich.enrich("stripe.com")["domain"] is None


def test_enrich_error_result_still_carries_the_domain(monkeypatch):
    site = {**SITE, "domain": "notion.so", "description": None, "about": None, "error": "Could not reach site"}
    monkeypatch.setattr(enrich, "get_description", lambda url: site)

    out = enrich.enrich("notion.so")

    assert out["error"] == "Could not reach site"
    assert out["domain"] == "notion.so"


class FakeRedis:
    """Just enough of redis for the cooldown code: exists and set, recording the ttl."""

    def __init__(self):
        self.keys = {}

    def exists(self, key):
        return key in self.keys

    def set(self, key, value, ex=None):
        self.keys[key] = ex


class FakeGemini:
    """Stands in for gemini_client. Each model either answers or raises what outcomes says."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.outcomes[model]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(parsed=outcome)


def client_error(code, status="SOME_STATUS"):
    return errors.ClientError(code, {"error": {"code": code, "message": f"synthetic {code}", "status": status}})


def fake_groq_client(company):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=company.model_dump_json()))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client.calls = calls
    return client


def use_fakes(monkeypatch, outcomes):
    fake_redis = FakeRedis()
    gemini = FakeGemini(outcomes)
    monkeypatch.setattr(enrich, "r", fake_redis)
    monkeypatch.setattr(enrich, "gemini_client", gemini)
    return fake_redis, gemini


FIRST, SECOND, THIRD = enrich.GEMINI_MODELS


def test_rate_limit_cools_the_model_down_and_tries_the_next_one(monkeypatch):
    fake_redis, gemini = use_fakes(monkeypatch, {FIRST: client_error(429), SECOND: COMPANY, THIRD: COMPANY})

    assert enrich.ask_gemini("prompt") == (COMPANY, SECOND)
    assert gemini.calls == [FIRST, SECOND]
    assert fake_redis.keys == {f"cooldown:{FIRST}": enrich.COOLDOWN_SECONDS}


def test_rate_limit_on_every_gemini_model_falls_through_to_groq(monkeypatch):
    outcomes = {model: client_error(429) for model in enrich.GEMINI_MODELS}
    fake_redis, gemini = use_fakes(monkeypatch, outcomes)
    groq = fake_groq_client(COMPANY)
    monkeypatch.setattr(enrich, "groq_client", groq)

    assert enrich.ask("prompt") == (COMPANY, enrich.GROQ_MODEL)
    assert gemini.calls == enrich.GEMINI_MODELS
    assert fake_redis.keys == {f"cooldown:{model}": enrich.COOLDOWN_SECONDS for model in enrich.GEMINI_MODELS}
    assert len(groq.calls) == 1


def test_model_not_found_gets_a_long_cooldown_and_the_next_model_is_tried(monkeypatch):
    fake_redis, gemini = use_fakes(monkeypatch, {FIRST: client_error(404, "NOT_FOUND"), SECOND: COMPANY, THIRD: COMPANY})

    assert enrich.ask_gemini("prompt") == (COMPANY, SECOND)
    assert gemini.calls == [FIRST, SECOND]
    assert fake_redis.keys == {f"cooldown:{FIRST}": enrich.NOT_FOUND_COOLDOWN_SECONDS}
    assert enrich.NOT_FOUND_COOLDOWN_SECONDS == 3600


def test_model_not_found_message_names_the_model(monkeypatch, capsys):
    use_fakes(monkeypatch, {FIRST: client_error(404, "NOT_FOUND"), SECOND: COMPANY, THIRD: COMPANY})

    enrich.ask_gemini("prompt")

    assert f"{FIRST} was not found" in capsys.readouterr().out


def test_bad_request_and_permission_errors_do_not_cool_the_model_down(monkeypatch):
    for code in (400, 401, 403):
        fake_redis, gemini = use_fakes(monkeypatch, {FIRST: client_error(code), SECOND: COMPANY, THIRD: COMPANY})

        assert enrich.ask_gemini("prompt") == (COMPANY, SECOND), code
        assert gemini.calls == [FIRST, SECOND], code
        assert fake_redis.keys == {}, code


def test_bad_key_on_every_gemini_model_still_reaches_groq(monkeypatch):
    use_fakes(monkeypatch, {model: client_error(403) for model in enrich.GEMINI_MODELS})
    monkeypatch.setattr(enrich, "groq_client", fake_groq_client(COMPANY))

    assert enrich.ask("prompt") == (COMPANY, enrich.GROQ_MODEL)


def test_a_cooled_model_is_skipped_on_the_next_call(monkeypatch):
    _, gemini = use_fakes(monkeypatch, {FIRST: client_error(429), SECOND: COMPANY, THIRD: COMPANY})

    enrich.ask_gemini("prompt")
    gemini.calls.clear()
    assert enrich.ask_gemini("prompt") == (COMPANY, SECOND)

    assert gemini.calls == [SECOND]


def test_server_error_still_cools_the_model_down_and_moves_on(monkeypatch):
    server_error = errors.ServerError(503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}})
    fake_redis, _ = use_fakes(monkeypatch, {FIRST: server_error, SECOND: COMPANY, THIRD: COMPANY})

    assert enrich.ask_gemini("prompt") == (COMPANY, SECOND)
    assert fake_redis.keys == {f"cooldown:{FIRST}": enrich.COOLDOWN_SECONDS}


def test_timeout_still_cools_the_model_down_and_moves_on(monkeypatch):
    fake_redis, _ = use_fakes(monkeypatch, {FIRST: httpx.ReadTimeout("slow"), SECOND: COMPANY, THIRD: COMPANY})

    assert enrich.ask_gemini("prompt") == (COMPANY, SECOND)
    assert fake_redis.keys == {f"cooldown:{FIRST}": enrich.COOLDOWN_SECONDS}


def test_an_unknown_error_is_not_swallowed(monkeypatch):
    fake_redis, gemini = use_fakes(monkeypatch, {FIRST: RuntimeError("boom"), SECOND: COMPANY, THIRD: COMPANY})

    with pytest.raises(RuntimeError, match="boom"):
        enrich.ask_gemini("prompt")

    assert gemini.calls == [FIRST]
    assert fake_redis.keys == {}


def test_enrich_ends_on_groq_when_gemini_is_rate_limited_everywhere(monkeypatch):
    use_fakes(monkeypatch, {model: client_error(429) for model in enrich.GEMINI_MODELS})
    monkeypatch.setattr(enrich, "groq_client", fake_groq_client(COMPANY))
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)

    out = enrich.enrich("stripe.com")

    assert out["error"] is None
    assert out["model"] == enrich.GROQ_MODEL
    assert out["company"] == COMPANY


def groq_bad_request():
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/chat"))
    return groq.BadRequestError("json_validate_failed", response=response, body=None)


def groq_auth_error():
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.groq.com/chat"))
    return groq.AuthenticationError("bad key", response=response, body=None)


def raising_groq_client(error):
    def create(**kwargs):
        raise error

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_groq_request_uses_low_reasoning_effort_and_a_4096_token_budget(monkeypatch):
    fake = fake_groq_client(COMPANY)
    monkeypatch.setattr(enrich, "groq_client", fake)

    enrich.ask_groq("prompt")

    sent = fake.calls[0]
    assert enrich.GROQ_REASONING_EFFORT == "low"
    assert enrich.GROQ_MAX_COMPLETION_TOKENS == 4096
    assert sent["model"] == enrich.GROQ_MODEL
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["reasoning_effort"] == "low"
    assert sent["max_completion_tokens"] == 4096


def test_groq_bad_request_returns_none_and_logs_status_and_message(monkeypatch, capsys):
    monkeypatch.setattr(enrich, "groq_client", raising_groq_client(groq_bad_request()))

    assert enrich.ask_groq("prompt") == (None, None)

    out = capsys.readouterr().out
    assert "400" in out
    assert "json_validate_failed" in out


def test_groq_bad_request_ends_the_job_as_all_models_busy(monkeypatch):
    use_fakes(monkeypatch, {model: client_error(429) for model in enrich.GEMINI_MODELS})
    monkeypatch.setattr(enrich, "groq_client", raising_groq_client(groq_bad_request()))
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)

    assert enrich.ask("prompt") == (None, None)
    out = enrich.enrich("stripe.com")

    assert "busy" in out["error"]
    assert out["company"] is None


def test_groq_authentication_error_still_propagates(monkeypatch):
    monkeypatch.setattr(enrich, "groq_client", raising_groq_client(groq_auth_error()))

    with pytest.raises(groq.AuthenticationError):
        enrich.ask_groq("prompt")


class ScriptedGroq:
    """Answers each model in turn from a dict: an exception is raised, a string is returned as the message."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes[kwargs["model"]]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))])


def groq_error(error_class, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.groq.com/chat"))
    return error_class(f"synthetic {status}", response=response, body=None)


SMALL, BIG = enrich.GROQ_MODELS


def test_groq_models_list_keeps_the_old_constant_as_the_first():
    assert enrich.GROQ_MODELS == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert enrich.GROQ_MODEL == enrich.GROQ_MODELS[0]


def test_groq_bad_request_on_the_first_model_moves_to_the_second(monkeypatch, capsys):
    fake = ScriptedGroq({SMALL: groq_bad_request(), BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    assert enrich.ask_groq("prompt") == (COMPANY, "openai/gpt-oss-120b")

    assert [call["model"] for call in fake.calls] == [SMALL, BIG]
    out = capsys.readouterr().out
    assert "400" in out
    assert "json_validate_failed" in out


def test_groq_answer_that_fails_validation_moves_to_the_second_model(monkeypatch):
    too_few = COMPANY.model_copy(update={"tailoring": ["a", "b", "c"]}).model_dump()
    too_few["tailoring"] = ["only one"]
    fake = ScriptedGroq({SMALL: json.dumps(too_few), BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    assert enrich.ask_groq("prompt") == (COMPANY, BIG)


def test_groq_bad_json_moves_to_the_second_model(monkeypatch):
    fake = ScriptedGroq({SMALL: "not json", BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    assert enrich.ask_groq("prompt") == (COMPANY, BIG)


def test_groq_not_found_on_the_first_model_moves_on(monkeypatch):
    fake = ScriptedGroq({SMALL: groq_error(groq.NotFoundError, 404), BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    assert enrich.ask_groq("prompt") == (COMPANY, BIG)


@pytest.mark.parametrize(
    "error",
    [
        groq_error(groq.InternalServerError, 500),
        groq_error(groq.RateLimitError, 429),
        groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com/chat")),
    ],
)
def test_groq_busy_errors_on_the_first_model_move_on(monkeypatch, error):
    fake = ScriptedGroq({SMALL: error, BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    assert enrich.ask_groq("prompt") == (COMPANY, BIG)


def test_groq_both_models_failing_gives_none_and_the_job_ends_as_busy(monkeypatch):
    use_fakes(monkeypatch, {model: client_error(429) for model in enrich.GEMINI_MODELS})
    fake = ScriptedGroq({SMALL: groq_bad_request(), BIG: "not json"})
    monkeypatch.setattr(enrich, "groq_client", fake)
    monkeypatch.setattr(enrich, "get_description", lambda url: SITE)

    assert enrich.ask_groq("prompt") == (None, None)
    out = enrich.enrich("stripe.com")

    assert "busy" in out["error"]
    assert out["company"] is None


def test_groq_authentication_error_on_the_first_model_propagates_without_trying_the_second(monkeypatch):
    fake = ScriptedGroq({SMALL: groq_auth_error(), BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    with pytest.raises(groq.AuthenticationError):
        enrich.ask_groq("prompt")
    assert len(fake.calls) == 1


def test_groq_log_line_is_truncated_to_200_characters(monkeypatch, capsys):
    long_error = groq.BadRequestError("x" * 500, response=httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/chat")), body=None)
    fake = ScriptedGroq({SMALL: long_error, BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    enrich.ask_groq("prompt")

    out = capsys.readouterr().out
    assert "x" * 200 in out
    assert "x" * 201 not in out


def test_every_groq_call_passes_reasoning_effort_and_the_token_budget(monkeypatch):
    fake = ScriptedGroq({SMALL: groq_bad_request(), BIG: COMPANY.model_dump_json()})
    monkeypatch.setattr(enrich, "groq_client", fake)

    enrich.ask_groq("prompt")

    for call in fake.calls:
        assert call["reasoning_effort"] == "low"
        assert call["max_completion_tokens"] == 4096
        assert call["response_format"]["json_schema"]["strict"] is True


def server_error(code, message):
    return errors.ServerError(code, {"error": {"code": code, "message": message, "status": "UNAVAILABLE"}})


def test_gemini_server_error_logs_the_code_and_message_and_cools_down(monkeypatch, capsys):
    fake_redis, gemini = use_fakes(
        monkeypatch, {FIRST: server_error(503, "The model is overloaded"), SECOND: COMPANY, THIRD: COMPANY}
    )

    assert enrich.ask_gemini("prompt") == (COMPANY, SECOND)

    out = capsys.readouterr().out
    assert f"{FIRST} returned a server error, cooling down for {enrich.COOLDOWN_SECONDS}s" in out
    assert "503" in out
    assert "The model is overloaded" in out
    assert fake_redis.keys == {f"cooldown:{FIRST}": enrich.COOLDOWN_SECONDS}
    assert gemini.calls == [FIRST, SECOND]


def test_gemini_server_error_message_is_truncated_to_200_characters(monkeypatch, capsys):
    use_fakes(monkeypatch, {FIRST: server_error(500, "y" * 500), SECOND: COMPANY, THIRD: COMPANY})

    enrich.ask_gemini("prompt")

    out = capsys.readouterr().out
    assert "y" * 200 in out
    assert "y" * 201 not in out
