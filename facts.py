"""Loads the demo fact sheets in facts/*.md. No network, no API clients.

A sheet is plain markdown: a `Repo:` line, a `Names:` line (what the demo is called in a
note), then three sections with one bullet per item: `## What it does`,
`## What it does not measure` and `## Numbers you may quote`.
"""

from pathlib import Path

FACTS_DIR = Path(__file__).parent / "facts"

SECTIONS = {
    "what it does": "does",
    "what it does not measure": "not_measured",
    "numbers you may quote": "numbers",
}


def load(name):
    """Return the sheet facts/<name>.md as a dict.

    Keys: file (the file name, used in messages), repo, names (list), does, not_measured and
    numbers (lists of bullet texts). A missing section is an empty list.
    """
    path = FACTS_DIR / f"{name}.md"
    sheet = {"file": path.name, "repo": "", "names": [], "does": [], "not_measured": [], "numbers": []}
    section = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("## "):
            section = SECTIONS.get(line[3:].strip().lower())
        elif line.startswith("- ") and section:
            sheet[section].append(line[2:].strip())
        elif line.startswith("Repo:"):
            sheet["repo"] = line[len("Repo:") :].strip()
        elif line.startswith("Names:"):
            sheet["names"] = [part.strip() for part in line[len("Names:") :].split(",") if part.strip()]
    return sheet


def prompt_text(sheet, letter):
    """The text the prompt shows for a demo: its cluster letter, then the 'what it does' bullets."""
    return f"{letter}: " + " ".join(sheet["does"])


def not_measured_line(*sheets):
    """One prompt line naming everything the demos do not measure, so the model never claims it."""
    phrases = []
    for sheet in sheets:
        phrases += [phrase for phrase in sheet["not_measured"] if phrase not in phrases]
    return "The two demos below do not measure or do any of these, so never claim them (see facts/*.md): " + ", ".join(phrases) + "."
