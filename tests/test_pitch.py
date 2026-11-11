import pytest

import pitch

GOOD_NOTE = (
    "Your agents need tuning to each client script before go live.\n"
    "Loom: [LOOM_URL] Repo: [REPO_URL]"
)

SITE = {
    "name": "Peakflo",
    "url": "https://www.peakflo.co/pricing",
    "title": "Peakflo | Accounts payable automation",
    "description": "Pay vendors faster with InvoiceFlow.",
    "about": "We help finance teams in India close the books.",
    "fde_roles": ["forward deployed"],
}


def note_with_last_line(last_line):
    return f"Short note about invoices.\n{last_line}"


def test_cluster_demos_cover_every_cluster():
    assert pitch.CLUSTERS == ("A", "B", "C", "D", "E", "F")
    assert set(pitch.CLUSTER_DEMOS) == set(pitch.CLUSTERS)
    assert set(pitch.CLUSTER_LABELS) == set(pitch.CLUSTERS)
    assert pitch.CLUSTER_DEMOS["A"] == "voice-agent-call-qa"
    assert pitch.CLUSTER_DEMOS["B"] == "invoice-exception-triage"
    for cluster in "CDEF":
        assert pitch.CLUSTER_DEMOS[cluster] == "none built"
    assert pitch.LOOM == "[LOOM_URL]"
    assert pitch.REPO == "[REPO_URL]"


def test_cluster_labels_match_the_spec_exactly():
    assert pitch.CLUSTER_LABELS == {
        "A": "voice and conversational agents",
        "B": "finance, insurance, back office",
        "C": "enterprise AI deployment (planned demo: SOP to agent kit, not built yet)",
        "D": "supply chain and physical ops (planned demo: capstone spin off, not built yet)",
        "E": "AI infra and dev tools (planned demo: migration validator, not built yet)",
        "F": "vertical SaaS (no default demo)",
    }


def test_none_note_does_not_raise():
    violations = pitch.check_pitch_note(None)
    assert any(pitch.LOOM in v and pitch.REPO in v for v in violations)
    assert pitch.candidate_names(None) == []
    assert pitch.ungrounded_names(None, "Peakflo") == []
    assert any(pitch.LOOM in v for v in pitch.pitch_violations(None, SITE))


def test_empty_note_reports_missing_placeholder_line():
    violations = pitch.check_pitch_note("")
    assert len(violations) == 1
    assert pitch.LOOM in violations[0] and pitch.REPO in violations[0]
    assert pitch.ungrounded_names("", "") == []


def test_ungrounded_handles_non_ascii_names_as_whole_tokens():
    cafe = "Caf\u00e9"
    assert pitch.candidate_names(f"We like {cafe} Zoho.") == ["We", cafe, "Zoho"]
    assert pitch.ungrounded_names(f"We like {cafe}.", f"The {cafe} team in India") == []
    assert pitch.ungrounded_names(f"We like {cafe}.", "Rahul") == [cafe]
    assert pitch.ungrounded_names(f"{cafe}{chr(0x2019)}s menu", "Rahul") == [cafe]


def test_style_rejects_151_words():
    filler = " ".join(["word"] * 147)
    note = f"{filler}\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert len(note.split()) == 151
    violations = pitch.check_pitch_note(note)
    assert any("150" in v for v in violations)


def test_style_accepts_exactly_150_words():
    filler = " ".join(["word"] * 146)
    note = f"{filler}\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert len(note.split()) == 150
    assert pitch.check_pitch_note(note) == []


@pytest.mark.parametrize(
    "char",
    [chr(code) for code in (0x2D, 0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)],
)
def test_style_rejects_each_dash_character(char):
    note = f"Go live{char}ready agents.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    violations = pitch.check_pitch_note(note)
    assert any("dash" in v for v in violations)


def test_style_requires_placeholders_on_last_line():
    assert pitch.check_pitch_note("Just a note.")
    assert pitch.check_pitch_note(note_with_last_line("Loom: [LOOM_URL]"))
    assert pitch.check_pitch_note(note_with_last_line("Repo: [REPO_URL] Loom: [LOOM_URL] bye"))
    assert pitch.check_pitch_note(note_with_last_line("Loom: [LOOM_URL] Repo: [REPO_URL] bye"))
    moved = "Loom: [LOOM_URL] Repo: [REPO_URL]\nAnd then more text."
    assert pitch.check_pitch_note(moved)


def test_style_ignores_trailing_blank_lines():
    note = GOOD_NOTE + "\n\n  \n"
    assert pitch.check_pitch_note(note) == []


def test_style_accepts_valid_note():
    assert pitch.check_pitch_note(GOOD_NOTE) == []


def test_ungrounded_flags_invented_product():
    note = "Your InvoiceGPT and Peakflo work well.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    corpus = "Peakflo automates accounts payable."
    assert pitch.ungrounded_names(note, corpus) == ["InvoiceGPT"]


def test_ungrounded_allows_site_words_case_insensitive():
    note = "Your PEAKFLO and Invoiceflow tools help Finance."
    corpus = "peakflo makes InvoiceFlow for finance teams"
    assert pitch.ungrounded_names(note, corpus) == []


def test_ungrounded_uses_whole_words_only():
    corpus = "Peakflow makes tools"
    assert pitch.ungrounded_names("Peak is great.", corpus) == ["Peak"]


def test_ungrounded_allows_allowlist_and_placeholders():
    note = (
        "The FDE team uses AI and an API in India.\n"
        "We speak English. Thanks, I hope Monday in March works.\n"
        "Loom: [LOOM_URL] Repo: [REPO_URL]"
    )
    assert pitch.ungrounded_names(note, "") == []


def test_ungrounded_strips_possessive():
    corpus = "Peakflo automates payables"
    assert pitch.ungrounded_names("Peakflo's customers are busy.", corpus) == []
    assert pitch.ungrounded_names(f"Peakflo{chr(0x2019)}s customers are busy.", corpus) == []
    assert pitch.ungrounded_names("Acme's customers are busy.", corpus) == ["Acme"]


def test_ungrounded_flags_inner_capitals_and_digits():
    names = pitch.ungrounded_names("try iPhone and G2 and 40 percent.", "")
    assert names == ["iPhone", "G2", "40"]


def test_ungrounded_ignores_lowercase_words():
    assert pitch.ungrounded_names("invoicegpt is invented but lower case.", "") == []


def test_ungrounded_returns_each_name_once():
    assert pitch.ungrounded_names("Acme and Acme again.", "") == ["Acme"]


def test_tally_zoho_hinglish_are_not_allowlisted():
    for word in ("Tally", "Zoho", "Hinglish"):
        assert word.lower() not in pitch.ALLOWED_WORDS


def test_tally_rejected_without_corpus_support_and_accepted_with_it():
    note = "Your finance teams export from Tally.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    without = {"name": "Acme", "description": "Invoices for finance teams."}
    with_tally = {"name": "Acme", "description": "Invoices from Tally for finance teams."}
    assert any("Tally" in v for v in pitch.pitch_violations(note, without))
    assert pitch.pitch_violations(note, with_tally) == []


def test_corpus_uses_all_documented_site_keys():
    site = {
        "name": "Nameco",
        "url": "https://www.hosty.example/page",
        "title": "Titleword",
        "description": "Descword",
        "about": "Aboutword",
        "fde_roles": ["solutions engineer"],
    }
    corpus = pitch.build_corpus(site)
    for word in ("Nameco", "hosty.example", "Titleword", "Descword", "Aboutword", "solutions engineer"):
        assert word in corpus


def test_corpus_copes_with_missing_keys():
    assert pitch.build_corpus({"name": "Nameco"}).strip() == "Nameco"
    assert pitch.build_corpus({"name": "Nameco", "fde_roles": None, "about": None}).strip() == "Nameco"


def test_pitch_violations_combines_style_and_grounding():
    violations = pitch.pitch_violations("Hello Zzyzx there.", SITE)
    assert any("Zzyzx" in v for v in violations)
    assert any("LOOM_URL" in v for v in violations)


def test_pitch_violations_empty_for_grounded_valid_note():
    note = "Peakflo's InvoiceFlow serves finance teams in India.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert pitch.pitch_violations(note, SITE) == []


def test_render_markdown_contains_note_and_tailoring():
    row = {
        "name": "Peakflo",
        "cluster": "B",
        "demo": "invoice-exception-triage",
        "hiring_fde": True,
        "pitch_note": GOOD_NOTE,
        "tailoring": ["Use rupee amounts", "Rename vendors", "Use GST terms"],
    }
    md = pitch.render_pitch_markdown(row)
    assert md.splitlines()[0] == "# Pitch for Peakflo"
    assert "Cluster: B" in md
    assert "Demo: invoice-exception-triage" in md
    assert "Hiring FDE: yes" in md
    assert "## Note\n\n" + GOOD_NOTE in md
    assert "## Tailoring" in md
    for item in row["tailoring"]:
        assert f"- {item}" in md
    assert md.index("## Note") < md.index("## Tailoring")


@pytest.mark.parametrize(
    ("value", "text"),
    [(True, "yes"), (False, "no"), (None, "unknown")],
)
def test_render_markdown_hiring_fde_three_values(value, text):
    row = {
        "name": "X",
        "cluster": "A",
        "demo": "d",
        "hiring_fde": value,
        "pitch_note": "n",
        "tailoring": ["a", "b", "c"],
    }
    assert f"Hiring FDE: {text}" in pitch.render_pitch_markdown(row)
