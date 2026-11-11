"""Pure helpers for the pitch engine: cluster to demo mapping, style checks,
the grounding guard and the markdown rendering. No network, no API clients.
"""

import re
from urllib.parse import urlparse

CLUSTERS = ("A", "B", "C", "D", "E", "F")

CLUSTER_LABELS = {
    "A": "voice and conversational agents",
    "B": "finance, insurance, back office",
    "C": "enterprise AI deployment (planned demo: SOP to agent kit, not built yet)",
    "D": "supply chain and physical ops (planned demo: capstone spin off, not built yet)",
    "E": "AI infra and dev tools (planned demo: migration validator, not built yet)",
    "F": "vertical SaaS (no default demo)",
}

# The demo comes from this table, never from the model.
CLUSTER_DEMOS = {
    "A": "voice-agent-call-qa",
    "B": "invoice-exception-triage",
    "C": "none built",
    "D": "none built",
    "E": "none built",
    "F": "none built",
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
# Stored lower case. Tally, Zoho and Hinglish are deliberately absent: a note
# may name them only when the target's own site does.
# Rule for adding a word: only words that are never plausible parts of a product
# or customer name. Words like best, kind, dear, regards, most, one and yet are
# excluded because Best Buy, Kind Snacks or Dear Health would slip through.
# Together, today, next, two and three are excluded too (Together AI, Two Sigma,
# Three the telecom).
# Accepted residual risk: first, second, third and the other ordinals stay
# allowed, because they are exactly the openers the model writes for "conclusion
# first, then 2 or 3 reasons", and rejecting them would reject grounded notes.
# So a real name made only of allowlisted words (for example First Round or
# First Data) is not caught unless a non allowlisted word in it is. This is a
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
    }
)  # fmt: skip

PLACEHOLDERS = (LOOM, REPO)

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


def candidate_names(note):
    """Words in the note that look like names: a capital letter, an inner capital or a digit."""
    text = note or ""
    for placeholder in PLACEHOLDERS:
        text = text.replace(placeholder, " ")

    candidates = []
    for token in WORD_PATTERN.findall(text):
        word = token.split("'")[0].split(CURLY_APOSTROPHE)[0]  # drops a possessive or contraction
        if not word:
            continue
        has_capital = word[0].isupper() or any(char.isupper() for char in word[1:])
        has_digit = any(char.isdigit() for char in word)
        if (has_capital or has_digit) and word not in candidates:
            candidates.append(word)
    return candidates


def ungrounded_names(note, corpus):
    """Return the names in the note that are neither allowlisted nor in the corpus.

    A name passes when its lower case form is in ALLOWED_WORDS or appears as a
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
