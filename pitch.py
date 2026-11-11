"""Pure helpers for the pitch engine: cluster to demo mapping, style checks,
the grounding guard and the markdown rendering. No network, no API clients.
"""

import re
from urllib.parse import urlparse

CLUSTERS = ("A", "B", "C", "D", "E", "F", "G")

CLUSTER_LABELS = {
    "A": "voice and conversational agents",
    "B": "finance, insurance, back office",
    "C": "enterprise AI deployment (planned demo: SOP to agent kit, not built yet)",
    "D": "supply chain and physical ops (planned demo: capstone spin off, not built yet)",
    "E": "AI infra and dev tools (planned demo: migration validator, not built yet)",
    "F": "vertical SaaS (no default demo)",
    "G": "computer use and desktop agents (no demo built yet)",
}

# The demo comes from this table, never from the model.
CLUSTER_DEMOS = {
    "A": "voice-agent-call-qa",
    "B": "invoice-exception-triage",
    "C": "none built",
    "D": "none built",
    "E": "none built",
    "F": "none built",
    "G": "none built",
}

LOOM = "[LOOM_URL]"
REPO = "[REPO_URL]"

MAX_WORDS = 150

# A hyphen plus the Unicode dashes and the minus sign.
DASH_CODE_POINTS = (0x2D, 0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)
DASH_CHARACTERS = "".join(chr(code) for code in DASH_CODE_POINTS)

# The curly apostrophe, built from its code point.
CURLY_APOSTROPHE = chr(0x2019)

# Capitalised words that may appear in a note without being on the site.
# Stored lower case. Only words that count as candidate names are checked (see
# candidate_names): a plain capitalised word at the start of a sentence is not a
# candidate, so this list mostly helps for mid sentence words such as Loom,
# Repo, India and GitHub. Tally, Zoho and Hinglish are deliberately absent: a
# note may name them only when the target's own site does.
# Rule for adding a word: only words that are never plausible parts of a product
# or customer name. Words like best, kind, dear, regards, most, one and yet are
# excluded because Best Buy, Kind Snacks or Dear Health would slip through.
# Together, today, next, two and three are excluded too (Together AI, Two Sigma,
# Three the telecom).
# Accepted residual risk: first, second, third and the other ordinals stay
# allowed, so a real name made only of allowlisted words (for example First Round
# or First Data) is not caught unless a non allowlisted word in it is. This is a
# deliberate trade off against false rejections of grounded notes.
ALLOWED_WORDS = frozenset(
    {
        # ordinals and connectives
        "first", "firstly", "second", "secondly", "third", "thirdly", "finally", "lastly",
        "then", "also", "additionally", "moreover", "however", "therefore",
        "overall", "because", "since", "although", "while", "when",
        "if", "and", "but", "so", "or",
        # prepositions and articles
        "the", "with", "without", "for", "from", "in", "on", "at", "by", "to", "of",
        "as", "a", "an", "that", "these", "those", "some", "many", "each", "every",
        "here", "there",
        # pronouns
        "we", "i", "you", "your", "this", "their", "our", "it", "they", "he", "she",
        # greetings
        "hi", "thanks", "please", "hello",
        # months
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        # days
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        # vocabulary from the user's own pitch
        "fde", "ai", "api", "llm", "qa", "sop", "ap", "gst", "csv", "erp",
        "loom", "repo", "github", "india", "indian", "english",
        # abbreviation tokens, so "Dr. Smith" with Smith on the site passes
        "dr", "mr", "mrs", "ms", "st", "inc", "ltd",
    }
)  # fmt: skip

PLACEHOLDERS = (LOOM, REPO)

# Stands in for a removed placeholder, so the word after it is not mistaken for
# the start of a sentence. It is not a word and not whitespace.
PLACEHOLDER_MARK = chr(0xFFFC)

# A plain capitalised word that opens a sentence is a name only when one of these follows it.
NAME_FOLLOWERS = frozenset({"ai", "labs", "inc"})

OPENING_MARKS = "\"'([{" + chr(0x201C) + chr(0x2018)
CLOSING_MARKS = "\"')]}" + chr(0x201D) + chr(0x2019)
SENTENCE_ENDS = ".!?"

# A period after one of these (lower case, dots stripped) does not end a sentence,
# so the next word is mid sentence. Accepted over flag: "He left Inc. Voice teams
# ship." treats Voice as mid sentence and flags it.
ABBREVIATIONS = frozenset({"e.g", "i.e", "vs", "etc", "dr", "mr", "mrs", "ms", "st", "inc", "ltd"})

# The last word of the text, letters and inner dots, followed by the final period ("e.g.").
LAST_WORD_BEFORE_PERIOD = re.compile(r"(?<![A-Za-z.])([A-Za-z]+(?:\.[A-Za-z]+)*)\.$")

# A list marker at the start of a line: optional bullet, then 1 or 2 digits or one letter,
# then a period or closing parenthesis and whitespace ("1. ", "2) ", "a) ", "* 3. ").
# The marker token is group 1.
LIST_MARKER = re.compile(r"[ \t]*(?:[\x2d*\u2022][ \t]*)?(\d{1,2}|[A-Za-z])[.)]\s")
# The whole line before a word is just a marker (the word is the first of a list item).
LINE_IS_MARKER = re.compile(r"[ \t]*(?:[\x2d*\u2022][ \t]*)?(?:\d{1,2}|[A-Za-z])[.)]\s+")

# Words, with apostrophes kept inside so a possessive stays attached to its word.
# Unicode aware: [^\\W_] is any letter or digit, so "Caf\u00e9" stays one token.
WORD_PATTERN = re.compile(f"[^\\W_][^\\W_'{CURLY_APOSTROPHE}]*(?:['{CURLY_APOSTROPHE}][^\\W_]+)*", re.UNICODE)


def check_pitch_note(note):
    """Return the style violations of a pitch note. An empty list means it passes.

    Checks: at most 150 words, no hyphen or dash characters, and the last
    non blank line contains the Loom placeholder and ends with the repo one.
    """
    note = note or ""
    violations = []

    word_count = len(note.split())
    if word_count > MAX_WORDS:
        violations.append(f"note has {word_count} words, the limit is {MAX_WORDS}")

    found = [char for char in DASH_CHARACTERS if char in note]
    if found:
        shown = ", ".join(f"U+{ord(char):04X}" for char in found)
        violations.append(f"note contains a hyphen or dash character ({shown})")

    lines = [line.strip() for line in note.splitlines() if line.strip()]
    last_line = lines[-1] if lines else ""
    if LOOM not in last_line or not last_line.endswith(REPO):
        violations.append(f"last line must contain {LOOM} and end with {REPO}")

    return violations


def build_corpus(site):
    """Join the scraped text a note may legitimately name.

    Uses the site dict keys title, description, about, fde_roles (a list of
    matched role phrases, may be missing), name, and the host of url. Missing
    or None values are skipped, so old site dicts still work.
    """
    parts = [site.get("title"), site.get("description"), site.get("about"), site.get("name")]
    parts.extend(site.get("fde_roles") or [])
    url = site.get("url")
    if url:
        parts.append(urlparse(url).hostname)
    return " ".join(part for part in parts if part)


def is_mixed_token(word):
    """Say whether a word has an inner capital letter or a digit (InvoiceGPT, G2B, 40)."""
    return any(char.isupper() for char in word[1:]) or any(char.isdigit() for char in word)


def has_name_follower(text, matches, index):
    """Say whether the word after matches[index] is AI, Labs or Inc, next to it with only spaces between."""
    if index + 1 >= len(matches):
        return False
    following = matches[index + 1]
    between = text[matches[index].end() : following.start()]
    return not between.strip() and following.group().lower() in NAME_FOLLOWERS


def ends_with_abbreviation(core):
    """Say whether the text ends with an abbreviation and its period (e.g., vs., Dr., Inc.)."""
    found = LAST_WORD_BEFORE_PERIOD.search(core)
    return bool(found) and found.group(1).lower() in ABBREVIATIONS


def is_list_marker(text, position, end=None):
    """Say whether the token at position is a list marker such as 1 in "1. First reason".

    Without end, say whether the text from the start of the line up to position is
    only a marker (so the word at position is the first word of a list item).
    With end, say whether the token ending at end is the marker itself.
    """
    line_start = text.rfind("\n", 0, position) + 1
    if end is None:
        return bool(LINE_IS_MARKER.fullmatch(text[line_start:position]))
    found = LIST_MARKER.match(text, line_start)
    return bool(found) and found.start(1) == position and found.end(1) == end


def starts_sentence(text, position):
    """Say whether the word at position opens a sentence.

    True for the first word of the text, the first word after a newline, the first
    word of a numbered or lettered list item, and a word after . ! or ? plus
    whitespace. An opening quote or bracket right before the word is skipped. A
    colon or comma does not start a sentence, and neither does a period that ends
    an abbreviation such as e.g., i.e., vs., etc., Dr., Mr. or Inc.

    Accepted residual risks, kept on purpose: an ellipsis ("Wait... Zendesk
    helps.") counts as a sentence end, and an abbreviation that really ends a
    sentence is read as mid sentence (an over flag, never a miss).
    """
    before = text[:position].rstrip(OPENING_MARKS)
    stripped = before.rstrip()
    if not stripped:
        return True
    gap = before[len(stripped) :]
    if "\n" in gap:
        return True
    if gap and is_list_marker(text, len(before)):
        return True
    core = stripped.rstrip(CLOSING_MARKS)
    if not gap or not core or core[-1] not in SENTENCE_ENDS:
        return False
    return not (core[-1] == "." and ends_with_abbreviation(core))


def candidate_names(note):
    """Words in the note that look like a product or company name.

    A candidate is a token with an inner capital letter or a digit (InvoiceGPT,
    G2B, 40) wherever it appears, or a plain capitalised word that is not at the
    start of a sentence. A plain capitalised word at the start of a sentence is
    a candidate only when the next word is AI, Labs or Inc (Acme Labs, Together
    AI, Acme Inc.). Other sentence openers (Simulated, Engineers, Conclusion)
    are not candidates, so a single word invented company opening a sentence is
    not caught. That is deliberate: the guard is a name check, not a fact check.
    The same holds for the first word of a numbered list item ("1. Zendesk
    integrates"): the bare list number is never a candidate, and an invented
    single word name opening a list item escapes, an accepted residual risk.
    Digits elsewhere ("cuts errors by 40 percent") stay candidates.
    """
    text = note or ""
    for placeholder in PLACEHOLDERS:
        text = text.replace(placeholder, f" {PLACEHOLDER_MARK} ")

    matches = list(WORD_PATTERN.finditer(text))
    candidates = []
    for index, match in enumerate(matches):
        word = match.group().split("'")[0].split(CURLY_APOSTROPHE)[0]  # drops a possessive or contraction
        if not word or word in candidates:
            continue
        if is_list_marker(text, match.start(), match.end()):
            continue
        if is_mixed_token(word):
            candidates.append(word)
        elif word[0].isupper():
            opens_sentence = starts_sentence(text, match.start())
            if not opens_sentence or has_name_follower(text, matches, index):
                candidates.append(word)
    return candidates


def ungrounded_names(note, corpus):
    """Return the candidate names in the note that are neither allowlisted nor in the corpus.

    Candidates are the ones candidate_names finds. A name passes when its lower case form is in ALLOWED_WORDS or appears as a
    whole word, ignoring case, in the corpus.
    """
    missing = []
    for word in candidate_names(note):
        lower = word.lower()
        if lower in ALLOWED_WORDS:
            continue
        if re.search(rf"\b{re.escape(lower)}\b", corpus, re.IGNORECASE):
            continue
        missing.append(word)
    return missing


def pitch_violations(note, site):
    """Return style violations plus one line for the ungrounded names, if any."""
    violations = check_pitch_note(note)
    missing = ungrounded_names(note, build_corpus(site))
    if missing:
        violations.append("names not found on the site: " + ", ".join(missing))
    return violations


def render_pitch_markdown(row):
    """Render a companies row (a dict) as the markdown served by the pitch endpoint."""
    hiring = {True: "yes", False: "no"}.get(row.get("hiring_fde"), "unknown")
    bullets = [f"- {item}" for item in row.get("tailoring") or []]
    lines = [
        f"# Pitch for {row['name']}",
        "",
        f"Cluster: {row.get('cluster')}",
        f"Demo: {row.get('demo')}",
        f"Hiring FDE: {hiring}",
        "",
        "## Note",
        "",
        row.get("pitch_note") or "",
        "",
        "## Tailoring",
        "",
        *bullets,
    ]
    return "\n".join(lines) + "\n"
