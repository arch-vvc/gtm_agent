import re

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
    assert pitch.candidate_names(f"We like {cafe} Zoho.") == [cafe, "Zoho"]
    assert pitch.ungrounded_names(f"We like {cafe}.", f"The {cafe} team in India") == []
    assert pitch.ungrounded_names(f"We like {cafe}.", "Rahul") == [cafe]
    assert pitch.ungrounded_names(f"See {cafe}{chr(0x2019)}s menu", "Rahul") == [cafe]


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
    assert pitch.ungrounded_names("We like Peak.", corpus) == ["Peak"]


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
    assert pitch.ungrounded_names("Ask Acme's customers.", corpus) == ["Acme"]


def test_ungrounded_flags_inner_capitals_and_digits():
    names = pitch.ungrounded_names("try iPhone and G2 and 40 percent.", "")
    assert names == ["iPhone", "G2", "40"]


def test_ungrounded_ignores_lowercase_words():
    assert pitch.ungrounded_names("invoicegpt is invented but lower case.", "") == []


def test_ungrounded_returns_each_name_once():
    assert pitch.ungrounded_names("Try Acme and Acme again.", "") == ["Acme"]


def test_tally_zoho_hinglish_are_not_allowlisted():
    for word in ("Tally", "Zoho", "Hinglish"):
        assert word.lower() not in pitch.ALLOWED_WORDS


def test_tally_rejected_without_corpus_support_and_accepted_with_it():
    note = "Your finance teams export from Tally.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    without = {"name": "Acme", "description": "Invoices for finance teams."}
    with_tally = {"name": "Acme", "description": "Invoices from Tally for finance teams."}
    assert any("Tally" in v for v in pitch.pitch_violations(note, without))
    assert pitch.pitch_violations(note, with_tally) == []


GOODCO_SITE = {
    "name": "Goodco",
    "description": "Goodco handles invoices and purchase orders. We are hiring a forward deployed engineer.",
}


def test_sentence_openers_do_not_trigger_the_guard():
    note = (
        "First, Goodco matches invoices, purchase orders and payments for finance teams.\n"
        "Second, Goodco is hiring a forward deployed engineer, so deployment is a real focus.\n"
        "Loom: [LOOM_URL] Repo: [REPO_URL]"
    )
    assert pitch.pitch_violations(note, GOODCO_SITE) == []


def test_connectives_do_not_trigger_the_guard():
    note = (
        "Finally, Goodco matches invoices. However, purchase orders still drift.\n"
        "Overall, a forward deployed engineer helps. Also, payments follow.\n"
        "Loom: [LOOM_URL] Repo: [REPO_URL]"
    )
    assert pitch.pitch_violations(note, GOODCO_SITE) == []


# Trade off, on purpose: a single word invented company at the START of a sentence
# with no AI, Labs or Inc after it (for example "Acme integrates well with your
# stack.") is no longer caught. Flagging every sentence opener rejected grounded
# notes ("Simulated", "Engineers") and an allowlist cannot keep up. The grounding
# guard is a name check, not a fact check.
def test_single_word_invented_company_at_sentence_start_is_no_longer_flagged():
    note = "Acme integrates well with your stack.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert pitch.pitch_violations(note, GOODCO_SITE) == []


def test_invented_company_mid_sentence_is_still_flagged():
    note = "We integrate with Acme every day.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    violations = pitch.pitch_violations(note, GOODCO_SITE)
    assert any("Acme" in v for v in violations)


def test_opener_does_not_hide_an_invented_name_after_it():
    note = "First, Acme integrates well.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert pitch.ungrounded_names(note, "Goodco invoices") == ["Acme"]


def test_invented_product_and_mid_sentence_name_still_flagged_with_openers():
    note = "However, InvoiceGPT works. Goodco also pairs with Zorblax.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert pitch.ungrounded_names(note, "Goodco invoices") == ["InvoiceGPT", "Zorblax"]


def test_invented_figure_and_digit_token_still_flagged_with_openers():
    assert pitch.ungrounded_names("Overall, 40 teams and G2B help.", "") == ["40", "G2B"]


def test_tally_still_flagged_after_widening():
    note = "Also, finance teams export from Tally.\nLoom: [LOOM_URL] Repo: [REPO_URL]"
    assert any("Tally" in v for v in pitch.pitch_violations(note, GOODCO_SITE))


def test_allowlist_matching_is_case_insensitive():
    assert pitch.ungrounded_names("FIRST, then HOWEVER and Finally.", "") == []


NEW_ALLOWED_WORDS = [
    "First", "Firstly", "Second", "Secondly", "Third", "Thirdly", "Finally", "Lastly",
    "Then", "Also", "Additionally", "Moreover", "However", "Therefore",
    "Overall", "Because", "Since", "Although", "While", "When",
    "If", "And", "But", "So", "Or", "With", "Without", "For", "From", "In",
    "On", "At", "By", "To", "Of", "As", "A", "An", "That", "These", "Those", "Some",
    "Many", "Each", "Every", "Here", "There", "They",
    "He", "She", "Please", "Hello",
]  # fmt: skip

# Words that can be real product or customer names (Best Buy, Kind Snacks, Dear Health,
# Together AI, Two Sigma, Three the telecom).
NAME_LIKE_WORDS = ["Best", "Kind", "Dear", "Regards", "Most", "One", "Yet",
                   "Together", "Today", "Next", "Two", "Three"]  # fmt: skip


def test_together_ai_is_flagged_when_not_in_corpus():
    names = pitch.ungrounded_names("Together AI ships agents for your stack.", "Goodco invoices")
    assert "Together" in names


def test_together_ai_is_accepted_when_in_corpus():
    assert pitch.ungrounded_names("Together AI ships agents for your stack.", "Together AI is a customer") == []


@pytest.mark.parametrize("word", ["Next", "Today", "Two", "Three"])
def test_removed_words_mid_sentence_are_flagged_without_corpus(word):
    names = pitch.ungrounded_names(f"We hired {word} teams for Goodco.", "Goodco invoices")
    assert names == [word]


@pytest.mark.parametrize("word", ["Next", "Today", "Two", "Three"])
def test_removed_words_at_sentence_start_are_not_flagged(word):
    # Same trade off as above: a plain opener with no AI, Labs or Inc follower passes.
    assert pitch.ungrounded_names(f"{word} teams use Goodco.", "Goodco invoices") == []


@pytest.mark.parametrize("word", NEW_ALLOWED_WORDS)
def test_new_allowed_words_are_present(word):
    # Explicit literals above, deliberately not a copy of the module list.
    assert word.lower() in pitch.ALLOWED_WORDS


@pytest.mark.parametrize("word", NAME_LIKE_WORDS)
def test_name_like_words_are_not_allowlisted(word):
    assert word.lower() not in pitch.ALLOWED_WORDS


def test_best_buy_flags_buy_but_not_the_sentence_opener_best():
    names = pitch.ungrounded_names("Best Buy integrates with your stack.", "Goodco invoices")
    assert names == ["Buy"]
    mid = pitch.ungrounded_names("We call Best Buy often.", "Goodco invoices")
    assert mid == ["Best", "Buy"]


def test_best_buy_is_accepted_when_in_corpus():
    assert pitch.ungrounded_names("Best Buy integrates with your stack.", "Best Buy is a customer") == []


def test_every_allowed_word_is_one_plain_lower_case_word():
    for word in pitch.ALLOWED_WORDS:
        assert re.fullmatch(r"[a-z]+", word), word


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


# Synthetic site text for the Cekura note below. Not scraped, written for this test.
CEKURA_SITE = {
    "name": "Cekura",
    "url": "https://cekura.ai",
    "title": "Cekura | Testing for voice agents",
    "description": "Testing and monitoring for voice AI agents.",
    "about": "Cekura helps teams QA conversational agents before they go live.",
}

CEKURA_NOTE = (
    "Cekura could cut go live risk for your customers' voice agents.\n"
    "\n"
    "Voice teams ship scripts they cannot fully test. Simulated callers and a judge "
    "show the failing turns before launch. Engineers then fix one prompt and run again.\n"
    "\n"
    "Loom: [LOOM_URL] Repo: [REPO_URL]"
)


def test_simulated_and_engineers_sentence_openers_are_not_flagged():
    # The old rule rejected this note with "names not found on the site: Simulated, Engineers".
    corpus = pitch.build_corpus(CEKURA_SITE)
    assert pitch.ungrounded_names(CEKURA_NOTE, corpus) == []
    assert pitch.pitch_violations(CEKURA_NOTE, CEKURA_SITE) == []
    assert pitch.candidate_names("Simulated callers help.") == []


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("Try InvoiceGPT for your stack.", ["InvoiceGPT"]),
        ("Teams love G2B tools.", ["G2B"]),
        ("We integrate with Acme every day.", ["Acme"]),
        ("Acme Labs builds agents.", ["Acme", "Labs"]),
        ("Together AI ships models.", ["Together", "AI"]),
        ("Acme Inc. builds agents.", ["Acme", "Inc"]),
        ("Conclusion: Zendesk is a fit.", ["Zendesk"]),
        ("Our tool cuts errors by 40 percent.", ["40"]),
        ("Finance teams export from Tally.", ["Tally"]),
    ],
)
def test_product_like_names_are_still_candidates(note, expected):
    assert pitch.candidate_names(note) == expected
    assert pitch.ungrounded_names(note, "Goodco invoices") == [
        word for word in expected if word.lower() not in pitch.ALLOWED_WORDS
    ]


def test_mixed_case_and_digit_tokens_are_candidates_even_at_sentence_start():
    assert pitch.candidate_names("InvoiceGPT helps. G2B too. 40 teams agree.") == ["InvoiceGPT", "G2B", "40"]
    assert pitch.candidate_names("OpenAI ships. iPhone sells.") == ["OpenAI", "iPhone"]


def test_followers_labs_inc_and_ai_are_case_insensitive():
    assert pitch.candidate_names("Acme labs builds agents.") == ["Acme"]
    assert pitch.candidate_names("Acme ai builds agents.") == ["Acme"]
    assert pitch.candidate_names("Acme INC builds agents.") == ["Acme", "INC"]
    assert pitch.candidate_names("Acme builds agents.") == []
    assert pitch.candidate_names("Acme, Labs builds agents.") == ["Labs"]


@pytest.mark.parametrize(
    "note",
    [
        "Hello. Voice teams ship.",
        "Great! Voice teams ship.",
        "Really? Voice teams ship.",
        "Hello.\nVoice teams ship.",
        "Voice teams ship.",
        'Hello. "Voice teams ship."',
        "Hello. (Voice teams ship.)",
        'He said "Done." Voice teams ship.',
        "Hello.   Voice teams ship.",
    ],
)
def test_sentence_start_words_are_not_candidates(note):
    names = pitch.candidate_names(note)
    assert "Voice" not in names


@pytest.mark.parametrize(
    "note",
    [
        "Conclusion: Voice teams ship.",
        "Hello, Voice teams ship.",
        "Hello Voice teams ship.",
        'He said "Voice teams ship."',
        "See (Voice teams ship.)",
        "Hello.Voice teams ship.",
    ],
)
def test_words_after_colon_comma_or_mid_sentence_are_candidates(note):
    assert "Voice" in pitch.candidate_names(note)


def test_conclusion_opener_is_skipped_but_name_after_colon_is_checked():
    assert pitch.candidate_names("Conclusion: Cekura could cut risk.") == ["Cekura"]
    assert pitch.ungrounded_names("Conclusion: Cekura could cut risk.", "Goodco") == ["Cekura"]
    assert pitch.ungrounded_names("Conclusion: Cekura could cut risk.", "Cekura") == []


def test_placeholders_do_not_create_a_false_sentence_start():
    # Without the marker, removing the placeholder would leave "Done. Foo", a false start.
    assert pitch.candidate_names("Watch. [LOOM_URL] Foo and Bar") == ["Foo", "Bar"]
    assert pitch.candidate_names("[LOOM_URL] Foo is here.") == ["Foo"]
    assert pitch.candidate_names("Loom: [LOOM_URL] Repo: [REPO_URL]") == ["Repo"]
