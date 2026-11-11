from urllib.parse import urljoin

import httpx
import pytest
from bs4 import BeautifulSoup

import scrape
from scrape import (
    find_customers_url,
    get_customers_text,
    get_description,
    normalise_url,
)


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


# ---- customers page ----

BASE = "https://acme.com"


def links_page(*anchors):
    return BeautifulSoup("<html><body>" + "".join(anchors) + "</body></html>", "html.parser")


class FakeResponse:
    def __init__(self, text="", status_code=200, url=BASE):
        self.text = text
        self.status_code = status_code
        self.url = url

    @property
    def is_error(self):
        return self.status_code >= 400


# Synthetic Loom style example: a video messaging SaaS site. The home page does not
# say who buys it, the customers page names product, design and engineering teams.
HOME_PAGE = """
<html><head>
<title>Acme | Video messaging for work</title>
<meta name="description" content="Record your screen and camera and share a link.">
</head><body>
<a href="/about">About</a>
<a href="/customers">Customers</a>
<a href="/pricing">Pricing</a>
</body></html>
"""
HOME_PAGE_NO_CUSTOMERS = HOME_PAGE.replace('<a href="/customers">Customers</a>', "")
ABOUT_PAGE = "<html><body><p>Acme helps teams share knowledge without scheduling another meeting.</p></body></html>"
CUSTOMERS_PAGE = """
<html><body>
<h1>Teams at larger companies use Acme</h1>
<h2>Product, design and engineering teams</h2>
<p>Product managers at 500 plus person companies share roadmap updates with stakeholders.</p>
<p>Short blurb.</p>
<img src="/a.svg" alt="Atlassian logo">
<img src="/b.svg" alt="Hubspot Logo">
<img src="/c.svg" alt="Intercom">
<img src="/d.svg" alt="">
<img src="/e.svg">
</body></html>
"""


def fake_get(pages):
    """Return a fake httpx.get that serves pages (a dict of url to FakeResponse or exception)."""

    def get(url, **kwargs):
        page = pages.get(url)
        if page is None:
            return FakeResponse(status_code=404, url=url)
        if isinstance(page, Exception):
            raise page
        return page

    return get


def site_pages(customers_page):
    return {
        BASE: FakeResponse(HOME_PAGE, url=BASE),
        BASE + "/about": FakeResponse(ABOUT_PAGE, url=BASE + "/about"),
        BASE + "/customers": customers_page,
    }


@pytest.mark.parametrize(
    "href",
    [
        "/customers",
        "/customers/",
        "/Customers/",
        "/customers/atlassian",
        "/en/customers",
        "/resources/case-studies",
        "/customer-stories",
        "/case-studies",
        "/case-study/acme",
        "/use-cases",
        "/use-case/sales",
        "/en/customers/index",
    ],
)
def test_find_customers_url_matches_href_paths(href):
    soup = links_page(f'<a href="{href}">Read more</a>')

    assert find_customers_url(soup, BASE) == urljoin(BASE, href)


@pytest.mark.parametrize(
    "href",
    [
        "/customers-login",
        "/blog/customers-first",
        "/careers/use-cases-engineer",
        "/customers/login",
        "/customers/signin",
        "/customers/sign-in",
        "/customers/signup",
        "/customers/sign-up",
        "/support/customers",
        "/help/customers",
        "/careers/customers",
        "/jobs/customers",
    ],
)
def test_find_customers_url_rejects_lookalike_and_login_paths(href):
    soup = links_page(f'<a href="{href}">Read more</a>')

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_rejects_other_hosts_for_href_match():
    soup = links_page(
        '<a href="https://support.acme.com/customers/login">Read more</a>',
        '<a href="https://customers.example.org/">Read more</a>',
        '<a href="https://other.com/customers">Read more</a>',
    )

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_rejects_other_hosts_for_text_match():
    soup = links_page(
        '<a href="https://customers.example.org/">Customers</a>',
        '<a href="https://support.acme.com/why">Case studies</a>',
    )

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_accepts_www_variant_of_the_same_host():
    soup = links_page('<a href="https://www.acme.com/customers">Read more</a>')

    assert find_customers_url(soup, BASE) == "https://www.acme.com/customers"


def test_find_customers_url_accepts_bare_host_when_base_has_www():
    soup = links_page('<a href="https://ACME.com/customers">Read more</a>')

    assert find_customers_url(soup, "https://www.acme.com") == "https://ACME.com/customers"


@pytest.mark.parametrize(
    "text",
    ["Customers", "  Customer Stories ", "CASE STUDIES", "Case Studies", "Use cases", "Our customers", "Meet our customers"],
)
def test_find_customers_url_matches_visible_text(text):
    soup = links_page(f'<a href="/why-acme">{text}</a>')

    assert find_customers_url(soup, BASE) == BASE + "/why-acme"


@pytest.mark.parametrize(
    "text",
    ["Customers login", "Customer login", "Customers sign in", "Customers signin", "Customer log in", "Customer support", "Customers help"],
)
def test_find_customers_url_ignores_login_and_support_link_text(text):
    soup = links_page(f'<a href="/portal">{text}</a>')

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_prefers_href_over_text():
    soup = links_page('<a href="/stories">Customers</a>', '<a href="/case-studies">Read</a>')

    assert find_customers_url(soup, BASE) == BASE + "/case-studies"


@pytest.mark.parametrize("text", ["Customer support", "Customer service", "Customer success", "For customers", "Help for customers"])
def test_find_customers_url_ignores_support_style_navigation_text(text):
    # "Customer service" and "Customer success" never match the text pattern at all,
    # the others are skipped by the login, support, help and "for customers" rules.
    soup = links_page(f'<a href="/help">{text}</a>')

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_skips_mailto_tel_javascript_and_anchors():
    soup = links_page(
        '<a href="mailto:customers@acme.com">Customers</a>',
        '<a href="tel:+911234567890">Customers</a>',
        '<a href="javascript:void(0)">Customers</a>',
        '<a href="#customers">Customers</a>',
        '<a href="#case-studies">Read</a>',
    )

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_returns_none_when_nothing_matches():
    soup = links_page('<a href="/pricing">Pricing</a>', '<a href="/about">About</a>')

    assert find_customers_url(soup, BASE) is None


def test_find_customers_url_makes_relative_links_absolute():
    soup = links_page('<a href="customers">Customers</a>')

    assert find_customers_url(soup, "https://acme.com/en/") == "https://acme.com/en/customers"


def test_get_customers_text_extracts_headings_long_paragraphs_and_logo_alt_text(monkeypatch):
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(CUSTOMERS_PAGE))

    text = get_customers_text(BASE + "/customers")

    assert "Teams at larger companies use Acme" in text
    assert "Product, design and engineering teams" in text
    assert "Product managers at 500 plus person companies" in text
    assert "Short blurb." not in text
    assert "Atlassian" in text
    assert "Atlassian logo" not in text
    assert "Hubspot" in text
    assert "Hubspot Logo" not in text
    assert "Intercom" in text


def customers_text_for(monkeypatch, body):
    page = "<html><body>" + body + "</body></html>"
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(page))
    return get_customers_text(BASE + "/customers")


def test_get_customers_text_strips_logo_image_suffix(monkeypatch):
    text = customers_text_for(monkeypatch, '<img alt="Stripe logo image"><img alt="Notion Logo Image">')

    assert text.split("\n") == ["Stripe", "Notion"]


@pytest.mark.parametrize("alt", ["logo", "Logo", "  LOGO  ", "logo image"])
def test_get_customers_text_drops_alt_that_is_just_logo(monkeypatch, alt):
    text = customers_text_for(monkeypatch, f'<h2>Our customers</h2><img alt="{alt}">')

    assert text == "Our customers"


def test_get_customers_text_drops_long_alt_text(monkeypatch):
    long_alt = "A photo of a smiling team in an office, " + "x" * 30
    assert len(long_alt) > 60

    text = customers_text_for(monkeypatch, f'<h2>Our customers</h2><img alt="{long_alt}"><img alt="Zomato">')

    assert text.split("\n") == ["Our customers", "Zomato"]


def test_get_customers_text_keeps_alt_of_exactly_60_characters(monkeypatch):
    alt = "y" * 60

    assert customers_text_for(monkeypatch, f'<img alt="{alt}">') == alt


def test_get_customers_text_silently_drops_logo_without_alt(monkeypatch):
    text = customers_text_for(monkeypatch, '<h2>Our customers</h2><img src="/e.svg"><img src="/f.svg" alt="">')

    assert text == "Our customers"


def test_get_customers_text_removes_duplicates(monkeypatch):
    page = '<html><body><img alt="Atlassian logo"><img alt="Atlassian logo"><h2>Atlassian</h2></body></html>'
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(page))

    assert get_customers_text(BASE + "/customers").split("\n") == ["Atlassian"]


def test_get_customers_text_caps_at_2000_characters(monkeypatch):
    page = "<html><body>" + "".join(f"<h2>Customer heading number {i} " + "x" * 50 + "</h2>" for i in range(100)) + "</body></html>"
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(page))

    assert len(get_customers_text(BASE + "/customers")) == 2000


def test_get_customers_text_uses_headers_redirects_and_timeout(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse(CUSTOMERS_PAGE)

    monkeypatch.setattr(scrape.httpx, "get", get)

    get_customers_text(BASE + "/customers")

    assert calls == [{"headers": scrape.headers, "follow_redirects": True, "timeout": 10}]


def test_get_customers_text_returns_none_on_error_status(monkeypatch):
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(CUSTOMERS_PAGE, status_code=404))

    assert get_customers_text(BASE + "/customers") is None


def test_get_customers_text_returns_none_on_http_error(monkeypatch):
    def get(url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(scrape.httpx, "get", get)

    assert get_customers_text(BASE + "/customers") is None


def test_get_customers_text_returns_none_for_empty_page(monkeypatch):
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse("<html><body><p>Hi</p></body></html>"))

    assert get_customers_text(BASE + "/customers") is None


def test_get_customers_text_returns_none_without_url():
    assert get_customers_text(None) is None


def test_get_description_includes_customers_url_and_text(monkeypatch):
    monkeypatch.setattr(scrape.httpx, "get", fake_get(site_pages(FakeResponse(CUSTOMERS_PAGE))))

    site = get_description("acme.com")

    assert site["customers_url"] == BASE + "/customers"
    assert "Product, design and engineering teams" in site["customers"]
    assert site["title"] == "Acme | Video messaging for work"
    assert site["about_url"] == BASE + "/about"
    assert "share knowledge" in site["about"]
    assert site["error"] is None


def test_get_description_has_no_customers_when_home_page_does_not_link_one(monkeypatch):
    pages = {BASE: FakeResponse(HOME_PAGE_NO_CUSTOMERS), BASE + "/about": FakeResponse(ABOUT_PAGE)}
    monkeypatch.setattr(scrape.httpx, "get", fake_get(pages))

    site = get_description("acme.com")

    assert site["customers_url"] is None
    assert site["customers"] is None
    assert site["about"] is not None


def test_get_description_survives_a_failed_customers_fetch(monkeypatch):
    pages = site_pages(httpx.ReadTimeout("slow"))
    monkeypatch.setattr(scrape.httpx, "get", fake_get(pages))

    site = get_description("acme.com")

    assert site["customers_url"] == BASE + "/customers"
    assert site["customers"] is None
    assert site["error"] is None
    assert site["description"] == "Record your screen and camera and share a link."


def test_get_description_error_paths_have_customers_keys(monkeypatch):
    def unreachable(url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(scrape.httpx, "get", unreachable)
    site = get_description("acme.com")
    assert site["error"] == "Could not reach site"
    assert site["customers_url"] is None
    assert site["customers"] is None

    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(status_code=503))
    site = get_description("acme.com")
    assert site["error"] == "Site returned 503"
    assert site["customers_url"] is None
    assert site["customers"] is None


# ---- final domain after redirects ----


def test_get_description_domain_is_the_host_after_redirects(monkeypatch):
    redirected = FakeResponse(HOME_PAGE_NO_CUSTOMERS, url="https://www.notion.com/")
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: redirected)

    site = get_description("notion.so")

    assert site["domain"] == "notion.com"
    assert site["name"] == "Notion"


def test_get_description_domain_is_lowercased_and_drops_www(monkeypatch):
    response = FakeResponse(HOME_PAGE_NO_CUSTOMERS, url="https://WWW.Acme.COM/Home")
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: response)

    assert get_description("acme.com")["domain"] == "acme.com"


def test_get_description_domain_keeps_a_subdomain(monkeypatch):
    response = FakeResponse(HOME_PAGE_NO_CUSTOMERS, url="https://docs.acme.com/")
    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: response)

    assert get_description("docs.acme.com")["domain"] == "docs.acme.com"


def test_get_description_domain_on_error_paths_is_the_input_host(monkeypatch):
    def unreachable(url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(scrape.httpx, "get", unreachable)
    assert get_description("https://www.Notion.so/")["domain"] == "notion.so"

    monkeypatch.setattr(scrape.httpx, "get", lambda url, **kwargs: FakeResponse(status_code=503, url="https://www.notion.com/"))
    assert get_description("notion.so")["domain"] == "notion.so"
