"""Helpers that spot placeholder answers such as "Not available".

This module imports nothing heavy on purpose, so a cleanup script can use it
without building any API clients.
"""

import re
import string

# Unambiguous placeholders are junk when they start the answer as whole words,
# so "Not available, see site" is junk but "Nathan's bakeries" is not.
JUNK_PREFIXES=[
    "not available",
    "not specified",
    "not provided",
    "no information",
    "unavailable",
    "unspecified",
    "n/a",
]
# Ambiguous words are junk only when they are the whole answer,
# so "None" is junk but "None of the above insurance" is a real answer.
JUNK_WHOLE_ANSWERS={"na", "n a", "none", "unknown"}
JUNK_PATTERN=re.compile("^(" + "|".join(re.escape(phrase) for phrase in JUNK_PREFIXES) + r")(\W|$)")
# Curly single and double quotes, written as escapes to keep this file ASCII.
EDGE_CHARS=string.punctuation + string.whitespace + "\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f"
NOT_APPLICABLE_PATTERN=re.compile(r"\bn\s*[/.]\s*a\b")


def normalise(value):
    text=str(value or "").strip(EDGE_CHARS)
    text=" ".join(text.lower().split())
    # "n.a", "n / a" and "n/a" all become "n/a"
    return NOT_APPLICABLE_PATTERN.sub("n/a", text)


def is_junk(value):
    cleaned=normalise(value)
    return cleaned == "" or cleaned in JUNK_WHOLE_ANSWERS or bool(JUNK_PATTERN.match(cleaned))


def junk_fields(company):
    fields={
        "industry": company.industry,
        "what_they_sell": company.what_they_sell,
        "target_customer": company.target_customer,
    }
    return [field for field, value in fields.items() if is_junk(value)]


def describe_answer(value):
    return " ".join(str(value or "").split())[:40]
