"""The README and the two fact sheets must point at the same standalone demo repos."""

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
SHEETS = {
    "call-qa": (ROOT / "facts" / "call-qa.md").read_text(encoding="utf-8"),
    "invoice-exception-triage": (ROOT / "facts" / "invoice-exception-triage.md").read_text(encoding="utf-8"),
}
GITHUB_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+")


def built_demos_section():
    match = re.search(r"^## Built demos\n(.*?)(?=^## |\Z)", README, re.MULTILINE | re.DOTALL)
    assert match, "the README needs a '## Built demos' section"
    return match.group(1)


def repo_line_url(sheet):
    match = re.search(r"^Repo: (\S+)", sheet, re.MULTILINE)
    assert match, "the fact sheet needs a Repo: line"
    return match.group(1)


def test_readme_links_both_standalone_repos():
    urls = GITHUB_URL.findall(built_demos_section())
    assert len(set(urls)) == 2


def test_fact_sheets_carry_same_urls():
    section = built_demos_section()
    for sheet in SHEETS.values():
        assert repo_line_url(sheet) in section
    assert len({repo_line_url(sheet) for sheet in SHEETS.values()}) == 2


def test_links_are_github_not_local_paths():
    urls = [repo_line_url(sheet) for sheet in SHEETS.values()]
    urls += GITHUB_URL.findall(built_demos_section())
    for url in urls:
        assert GITHUB_URL.fullmatch(url), url
        assert "/Users/" not in url and "file:" not in url


@pytest.mark.skipif(os.environ.get("RELEASE_CHECK") != "1", reason="set RELEASE_CHECK=1 before publishing")
def test_no_placeholder_links_remain():
    for text in [README, *SHEETS.values()]:
        assert "REPLACE_ME" not in text
