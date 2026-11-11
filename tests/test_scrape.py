import httpx
import pytest
from bs4 import BeautifulSoup

import scrape
from scrape import find_careers_url, find_fde_roles, normalise_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("stripe.com", "https://stripe.com"),
        ("https://stripe.com", "https://stripe.com"),
        ("http://stripe.com", "https://stripe.com"),
        ("HTTPS://Stripe.com", "https://stripe.com"),
        ("  stripe.com  ", "https://stripe.com"),
        ("www.stripe.com", "https://stripe.com"),
        ("https://www.stripe.com/", "https://stripe.com"),
        ("stripe.com/about/", "https://stripe.com/about"),
        ("stripe.com/about?x=1#top", "https://stripe.com/about"),
        ("https://docs.stripe.com/api", "https://docs.stripe.com/api"),
    ],
)
def test_normalise_url_valid(raw, expected):
    assert normalise_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "stripe", "localhost", "https://localhost"])
def test_normalise_url_rejects_hosts_without_a_dot(raw):
    assert normalise_url(raw) is None



class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code

    @property
    def is_error(self):
        return self.status_code >= 400


def soup_of(html):
    return BeautifulSoup(html, "html.parser")


def fake_get(pages):
    """Build a replacement for httpx.get that serves a dict of url to response or exception."""

    def get(url, **kwargs):
        page = pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    return get


HOME = (
    "<html><head><title>Acme</title>"
    '<meta name="description" content="Synthetic test company"></head>'
    '<body><a href="/careers">Careers</a></body></html>'
)


def home_page():
    return FakeResponse(HOME, "https://acme.com")


def careers_page(body):
    return FakeResponse(f"<html><body>{body}</body></html>", "https://acme.com/careers")


@pytest.mark.parametrize(
    "html, expected",
    [
        ('<a href="/careers">Work here</a>', "https://acme.com/careers"),
        ('<a href="/Jobs/">Open roles</a>', "https://acme.com/Jobs/"),
        ('<a href="/team">Careers</a>', "https://acme.com/team"),
        ('<a href="/x">Join Us</a>', "https://acme.com/x"),
        ('<a href="/join-us">Team</a>', "https://acme.com/join-us"),
        ('<a href="/y">Work with us</a>', "https://acme.com/y"),
        ('<a href="/work-with-us">Team</a>', "https://acme.com/work-with-us"),
        ('<a href="https://jobs.lever.co/acme">Hiring</a>', "https://jobs.lever.co/acme"),
        ('<a href="/about">About</a>', None),
    ],
)
def test_find_careers_url_matches_href_and_text(html, expected):
    assert find_careers_url(soup_of(html), "https://acme.com") == expected


def test_find_careers_url_skips_anchors():
    html = '<a href="#careers">Careers</a><a href="/jobs">Jobs</a>'
    assert find_careers_url(soup_of(html), "https://acme.com") == "https://acme.com/jobs"
    assert find_careers_url(soup_of('<a href="#careers">Careers</a>'), "https://acme.com") is None


def test_find_fde_roles_matches_hyphenated_forward_deployed():
    text = "Open roles: Forward-Deployed Engineer, Solutions Architect, Forward deployed lead"
    assert sorted(find_fde_roles(text)) == ["forward deployed", "solutions architect"]


def test_find_fde_roles_empty_for_unrelated_jobs():
    assert find_fde_roles("Account Executive, Office Manager, Backend Developer") == []
    assert find_fde_roles("") == []
    assert find_fde_roles(None) == []


def test_get_description_sets_hiring_fde_true_false_none(monkeypatch):
    cases = [
        (careers_page("<h1>Forward Deployed Engineer</h1>"), True, ["forward deployed"]),
        (careers_page("<h1>Account Executive</h1>"), False, []),
        (careers_page(""), None, []),
    ]
    for careers, hiring_fde, roles in cases:
        pages = {"https://acme.com": home_page(), "https://acme.com/careers": careers}
        monkeypatch.setattr(scrape.httpx, "get", fake_get(pages))
        site = scrape.get_description("acme.com")
        assert site["careers_url"] == "https://acme.com/careers"
        assert site["hiring_fde"] is hiring_fde
        assert site["fde_roles"] == roles
        assert site["error"] is None


def test_get_description_hiring_fde_none_without_link_or_on_failed_fetch(monkeypatch):
    no_link = FakeResponse("<html><title>Acme</title><body>Hi</body></html>", "https://acme.com")
    monkeypatch.setattr(scrape.httpx, "get", fake_get({"https://acme.com": no_link}))
    site = scrape.get_description("acme.com")
    assert (site["careers_url"], site["hiring_fde"], site["fde_roles"]) == (None, None, [])

    for failure in (FakeResponse("", "https://acme.com/careers", 404), httpx.ConnectError("boom")):
        pages = {"https://acme.com": home_page(), "https://acme.com/careers": failure}
        monkeypatch.setattr(scrape.httpx, "get", fake_get(pages))
        site = scrape.get_description("acme.com")
        assert site["careers_url"] == "https://acme.com/careers"
        assert site["hiring_fde"] is None
        assert site["fde_roles"] == []


def test_get_careers_text_caps_length_and_handles_missing_url(monkeypatch):
    long_page = careers_page("word " * 10000)
    monkeypatch.setattr(scrape.httpx, "get", fake_get({"https://acme.com/careers": long_page}))
    assert len(scrape.get_careers_text("https://acme.com/careers")) == 20000
    assert scrape.get_careers_text(None) is None


def test_get_description_error_paths_have_careers_keys(monkeypatch):
    expected = {"careers_url": None, "hiring_fde": None, "fde_roles": [], "url": "https://acme.com"}

    monkeypatch.setattr(scrape.httpx, "get", fake_get({"https://acme.com": httpx.ConnectError("boom")}))
    unreachable = scrape.get_description("acme.com")
    assert unreachable["error"] == "Could not reach site"

    server_error = FakeResponse("", "https://acme.com", 500)
    monkeypatch.setattr(scrape.httpx, "get", fake_get({"https://acme.com": server_error}))
    failing = scrape.get_description("acme.com")
    assert failing["error"] == "Site returned 500"

    for site in (unreachable, failing):
        for key, value in expected.items():
            assert site[key] == value


def test_get_description_returns_normalised_url_on_success(monkeypatch):
    pages = {"https://acme.com/x": home_page(), "https://acme.com/careers": careers_page("Jobs")}
    monkeypatch.setattr(scrape.httpx, "get", fake_get(pages))
    assert scrape.get_description("HTTP://www.Acme.com/x/")["url"] == "https://acme.com/x"
