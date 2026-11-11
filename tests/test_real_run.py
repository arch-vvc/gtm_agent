import csv

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


CSV_HEADER = [
    "url",
    "name",
    "cluster",
    "demo",
    "hiring_fde",
    "cluster_reason",
    "customer_pain",
    "tailoring",
    "pitch_note",
    "pitch_error",
    "model",
    "error",
]


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_help_mentions_csv_without_api_keys(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        real_run.main(["--help"])

    assert exit_info.value.code == 0
    assert "--csv" in capsys.readouterr().out


def test_csv_has_header_a_good_row_and_an_errored_row(monkeypatch, tmp_path, capsys):
    path = tmp_path / "results.csv"
    company = make_company("B", AP_NOTE)
    fake_models(monkeypatch, [(company, "gemini-3.5-flash")])
    real_enrich = enrich.enrich

    def fake_enrich(url):
        if url == "broken.example":
            raise RuntimeError("API key not valid")
        return real_enrich(url)

    monkeypatch.setattr(enrich, "enrich", fake_enrich)

    code = real_run.main(["--csv", str(path), "ledgerly.example", "broken.example"])

    rows = read_csv(path)
    assert code == 1
    assert rows[0] == CSV_HEADER
    assert len(rows) == 3
    good = dict(zip(CSV_HEADER, rows[1]))
    assert good["url"] == "ledgerly.example"
    assert good["name"] == "Ledgerly"
    assert good["cluster"] == "B"
    assert good["demo"] == "invoice-exception-triage"
    assert good["cluster_reason"] == company.cluster_reason
    assert good["customer_pain"] == company.customer_pain
    assert good["pitch_note"] == AP_NOTE
    assert good["pitch_error"] == ""
    assert good["model"] == "gemini-3.5-flash"
    assert good["error"] == ""
    bad = dict(zip(CSV_HEADER, rows[2]))
    assert bad["url"] == "broken.example"
    assert bad["error"] == "RuntimeError: API key not valid"
    assert bad["cluster"] == ""
    assert bad["pitch_note"] == ""
    assert f"{path}" in capsys.readouterr().out


def test_csv_site_error_row_has_the_error_text(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    monkeypatch.setattr(enrich, "get_description", lambda url: {**AP_SITE, "error": "Site returned 403"})

    code = real_run.main(["--csv", str(path), "broken.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert code == 1
    assert row["error"] == "Site returned 403"
    assert row["cluster"] == ""
    assert row["tailoring"] == ""


def test_csv_pitch_note_with_commas_quotes_and_newlines_round_trips(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    note = AP_NOTE + ' Line two, with "quotes", and commas.\nLine three.'
    monkeypatch.setattr(real_run.pitch, "pitch_violations", lambda pitch_note, site: [])
    fake_models(monkeypatch, [(make_company("B", note), "gemini-3.5-flash")])

    real_run.main(["--csv", str(path), "ledgerly.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert row["pitch_note"] == note


def test_csv_tailoring_is_joined_with_pipes(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])

    real_run.main(["--csv", str(path), "ledgerly.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert row["tailoring"] == "Use Tally style sample data | Name personas after AP clerks | Say GST not VAT"


@pytest.mark.parametrize(
    ("value", "cell"),
    [(True, "true"), (False, "false"), (None, "")],
)
def test_csv_hiring_fde_is_true_false_or_empty(monkeypatch, tmp_path, value, cell):
    path = tmp_path / "results.csv"
    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])
    real_enrich = enrich.enrich

    def fake_enrich(url):
        return {**real_enrich(url), "hiring_fde": value}

    monkeypatch.setattr(enrich, "enrich", fake_enrich)

    real_run.main(["--csv", str(path), "ledgerly.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert row["hiring_fde"] == cell


def test_csv_guard_failed_row_has_empty_pitch_note_and_the_pitch_error(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    bad = (make_company("B", INVENTED_NOTE), "gemini-3.5-flash")
    fake_models(monkeypatch, [bad, bad])

    code = real_run.main(["--csv", str(path), "ledgerly.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert code == 0
    assert row["pitch_note"] == ""
    assert row["pitch_error"].startswith("Pitch note rejected")
    assert row["cluster"] == "B"


def test_csv_creates_the_parent_directory(monkeypatch, tmp_path):
    path = tmp_path / "reports" / "nested" / "results.csv"
    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])

    real_run.main(["--csv", str(path), "ledgerly.example"])

    assert path.is_file()


def test_no_csv_file_is_written_without_the_flag(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    fake_models(monkeypatch, [(make_company("B", AP_NOTE), "gemini-3.5-flash")])

    code = real_run.main(["ledgerly.example"])

    assert code == 0
    assert list(tmp_path.iterdir()) == []
    assert "CSV" not in capsys.readouterr().out


def test_exception_secret_is_redacted_in_csv_and_stdout(monkeypatch, tmp_path, capsys):
    path = tmp_path / "results.csv"

    def fake_enrich(url):
        raise RuntimeError("401 bad key sk-test-123 for header Authorization")

    monkeypatch.setattr(enrich, "enrich", fake_enrich)

    code = real_run.main(["--csv", str(path), "broken.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert code == 1
    assert "sk-test-123" not in path.read_text(encoding="utf-8")
    assert "sk-test-123" not in capsys.readouterr().out
    assert row["error"].startswith("RuntimeError: 401 bad key [REDACTED]")


def test_env_secret_value_is_redacted(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gem-value-98765")
    monkeypatch.setenv("SHORT_TOKEN", "abc")

    text = real_run.safe_message(RuntimeError("rejected fake-gem-value-98765 and abc"))

    assert "fake-gem-value-98765" not in text
    assert "[REDACTED]" in text
    assert "and abc" in text


@pytest.mark.parametrize(
    "secret",
    [
        "AIzaSyA1234567890abcdef",
        "gsk_abcdef1234567890",
        "Bearer abcdef123456",
        "Authorization: Basic dXNlcjpwYXNz",
        "x-goog-api-key: zzzz1234yyyy",
    ],
)
def test_common_key_shapes_are_redacted(secret):
    text = real_run.safe_message(RuntimeError(f"failed with {secret} in request"))

    assert "[REDACTED]" in text
    for piece in secret.split()[-1:]:
        assert piece not in text


def test_normal_message_is_unchanged():
    assert real_run.safe_message(RuntimeError("Site returned 403")) == "RuntimeError: Site returned 403"


def test_message_whitespace_is_collapsed_and_long_message_truncated():
    text = real_run.safe_message(RuntimeError("line one\n\nline   two\t" + "x" * 1000))

    assert text.startswith("RuntimeError: line one line two x")
    assert len(text) == 300


def test_csv_cluster_reason_formula_gets_an_apostrophe(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    reason = '=HYPERLINK("http://evil","x")'
    fake_models(monkeypatch, [(make_company("B", AP_NOTE, cluster_reason=reason), "gemini-3.5-flash")])

    real_run.main(["--csv", str(path), "ledgerly.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert row["cluster_reason"] == "'" + reason


@pytest.mark.parametrize("first", ["=", "+", "-", "@", "\t", "\r"])
def test_cell_prefixes_an_apostrophe_for_formula_starts(first):
    assert real_run.cell(first + "cmd") == "'" + first + "cmd"


def test_cell_leaves_normal_text_digits_and_empty_alone():
    assert real_run.cell("Hello +world") == "Hello +world"
    assert real_run.cell("42 items") == "42 items"
    assert real_run.cell("") == ""
    assert real_run.cell(None) == ""
    assert real_run.cell(True) == "true"


def test_csv_pitch_note_starting_with_plus_gets_an_apostrophe(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    note = "+cmd " + AP_NOTE
    monkeypatch.setattr(real_run.pitch, "pitch_violations", lambda pitch_note, site: [])
    fake_models(monkeypatch, [(make_company("B", note), "gemini-3.5-flash")])

    real_run.main(["--csv", str(path), "ledgerly.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert row["pitch_note"] == "'" + note


def test_csv_error_text_starting_with_a_formula_char_gets_an_apostrophe(monkeypatch, tmp_path):
    path = tmp_path / "results.csv"
    monkeypatch.setattr(enrich, "get_description", lambda url: {**AP_SITE, "error": "=1+1"})

    real_run.main(["--csv", str(path), "broken.example"])

    row = dict(zip(CSV_HEADER, read_csv(path)[1]))
    assert row["error"] == "'=1+1"


def test_csv_pointing_at_a_directory_fails_before_any_work(monkeypatch, tmp_path, capsys):
    def boom(url):
        raise AssertionError("must not scrape")

    monkeypatch.setattr(enrich, "get_description", boom)
    monkeypatch.setattr(enrich, "ask", boom)

    with pytest.raises(SystemExit) as exit_info:
        real_run.main(["--csv", str(tmp_path), "ledgerly.example"])

    assert exit_info.value.code != 0
    assert "directory" in capsys.readouterr().err


def test_csv_help_mentions_overwrite_and_apostrophe(capsys):
    with pytest.raises(SystemExit):
        real_run.main(["--help"])

    out = " ".join(capsys.readouterr().out.split())
    assert "overwritten" in out
    assert "apostrophe" in out
