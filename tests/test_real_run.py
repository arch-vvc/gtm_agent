import pytest

import enrich
from scripts import real_run
from tests.test_pitch_engine import AP_NOTE, AP_SITE, INVENTED_NOTE, make_company


def fake_models(monkeypatch, answers):
    monkeypatch.setattr(enrich, "get_description", lambda url: AP_SITE)
    remaining = list(answers)
    monkeypatch.setattr(enrich, "ask", lambda prompt: remaining.pop(0))


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exit_info:
        real_run.main(["--help"])

    assert exit_info.value.code == 0
    assert "--provider" in capsys.readouterr().out


def test_provider_flag_sets_enrich_providers(monkeypatch):
    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])
    monkeypatch.setattr(enrich, "PROVIDERS", [])

    real_run.main(["--provider", "groq", "ledgerly.example"])

    assert enrich.PROVIDERS == [enrich.ask_groq]


def test_prints_json_and_markdown_and_exits_zero(monkeypatch, capsys):
    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])

    code = real_run.main(["ledgerly.example"])

    out = capsys.readouterr().out
    assert code == 0
    assert '"demo": "invoice-exception-triage"' in out
    assert "# Pitch for Ledgerly" in out
    assert "provider gemini, model gemini-3.5-flash" in out
    assert "WARNING" not in out


def test_warns_when_pitch_note_is_null(monkeypatch, capsys):
    bad = (make_company("B", INVENTED_NOTE), "gemini-3.5-flash")
    fake_models(monkeypatch, [bad, bad])

    code = real_run.main(["ledgerly.example"])

    out = capsys.readouterr().out
    assert code == 0
    assert "WARNING: pitch_note is NULL. pitch_error: " in out
    assert "InvoiceGPT" in out


def test_an_exception_from_one_url_does_not_stop_the_rest(monkeypatch, capsys):
    seen = []

    def fake_enrich(url):
        seen.append(url)
        if url == "first.example":
            raise RuntimeError("API key not valid")
        return real_enrich(url)

    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])
    real_enrich = enrich.enrich
    monkeypatch.setattr(enrich, "enrich", fake_enrich)

    code = real_run.main(["first.example", "second.example"])

    out = capsys.readouterr().out
    assert seen == ["first.example", "second.example"]
    assert "ERROR: RuntimeError: API key not valid" in out
    assert "# Pitch for Ledgerly" in out
    assert "1 of 2 URLs enriched" in out
    assert code != 0


def test_exit_code_is_non_zero_when_a_url_errors(monkeypatch, capsys):
    monkeypatch.setattr(enrich, "get_description", lambda url: {**AP_SITE, "error": "Site returned 403"})

    code = real_run.main(["broken.example"])

    assert code == 1
    assert "ERROR: Site returned 403" in capsys.readouterr().out
