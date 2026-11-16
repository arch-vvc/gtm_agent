import httpx
import pytest

import scrape

REFUSED = "Refused: not a public web address"
PUBLIC = "93.184.216.34"


class Resolver:
    """Injectable resolver: a dict of host to addresses, and a record of what was asked."""

    def __init__(self, table=None):
        self.table = table or {}
        self.asked = []

    def __call__(self, host):
        self.asked.append(host)
        if host not in self.table:
            raise OSError("no such host")
        return self.table[host]


def transport_for(handler):
    calls = []

    def wrapped(request):
        calls.append(str(request.url))
        return handler(request)

    return httpx.MockTransport(wrapped), calls


def ok(request):
    return httpx.Response(200, text="<html><body>hello</body></html>")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://localhost:8000",
        "http://10.0.0.5",
        "http://169.254.169.254",
        "http://[::1]",
        "ftp://example.com",
        "https://example.com:8443",
        "http://0.0.0.0",
        "http://192.168.1.1/admin",
        "http://224.0.0.1",
        "http://[fe80::1]",
        "http://[::ffff:127.0.0.1]",
        "http://printer.local",
        "http://db.internal",
        "http://LOCALHOST",
        "file:///etc/passwd",
    ],
)
def test_refused_urls_make_no_request(url):
    transport, calls = transport_for(ok)
    resolver = Resolver({"example.com": [PUBLIC], "printer.local": [PUBLIC], "db.internal": [PUBLIC], "localhost": [PUBLIC]})
    with pytest.raises(scrape.RefusedURL):
        scrape.fetch(url, resolver=resolver, transport=transport)
    assert calls == []


def test_refused_error_text_is_exact():
    assert str(scrape.RefusedURL()) == REFUSED


def test_host_resolving_to_one_public_and_one_private_address_is_refused():
    transport, calls = transport_for(ok)
    resolver = Resolver({"mixed.example.com": [PUBLIC, "10.0.0.5"]})
    with pytest.raises(scrape.RefusedURL):
        scrape.fetch("https://mixed.example.com", resolver=resolver, transport=transport)
    assert calls == []


def test_ipv6_private_address_from_dns_is_refused():
    transport, calls = transport_for(ok)
    resolver = Resolver({"v6.example.com": ["fd00::1"]})
    with pytest.raises(scrape.RefusedURL):
        scrape.fetch("https://v6.example.com", resolver=resolver, transport=transport)
    assert calls == []


def test_normal_public_host_is_allowed():
    transport, calls = transport_for(ok)
    resolver = Resolver({"example.com": [PUBLIC]})
    response = scrape.fetch("https://example.com/page", resolver=resolver, transport=transport)
    assert response.status_code == 200
    assert "hello" in response.text
    assert calls == ["https://example.com/page"]


def test_ports_80_and_443_are_allowed():
    resolver = Resolver({"example.com": [PUBLIC]})
    for url in ("http://example.com:80", "https://example.com:443"):
        transport, calls = transport_for(ok)
        assert scrape.fetch(url, resolver=resolver, transport=transport).status_code == 200
        assert len(calls) == 1


def test_public_host_redirecting_to_private_host_is_refused_at_the_hop():
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})
        return httpx.Response(200, text="secret")

    transport, calls = transport_for(handler)
    resolver = Resolver({"example.com": [PUBLIC]})
    with pytest.raises(scrape.RefusedURL):
        scrape.fetch("https://example.com", resolver=resolver, transport=transport)
    assert calls == ["https://example.com"]


def test_redirect_to_a_host_that_resolves_private_is_refused():
    def handler(request):
        return httpx.Response(301, headers={"location": "https://sneaky.example.org/"})

    transport, calls = transport_for(handler)
    resolver = Resolver({"example.com": [PUBLIC], "sneaky.example.org": ["127.0.0.1"]})
    with pytest.raises(scrape.RefusedURL):
        scrape.fetch("https://example.com", resolver=resolver, transport=transport)
    assert calls == ["https://example.com"]


def test_relative_redirects_are_followed_and_checked():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="done")

    transport, calls = transport_for(handler)
    resolver = Resolver({"example.com": [PUBLIC]})
    response = scrape.fetch("https://example.com/start", resolver=resolver, transport=transport)
    assert response.text == "done"
    assert str(response.url) == "https://example.com/final"
    assert calls == ["https://example.com/start", "https://example.com/final"]


def test_five_redirects_are_followed():
    def handler(request):
        step = int(request.url.path.strip("/") or 0)
        if step < 5:
            return httpx.Response(302, headers={"location": f"/{step + 1}"})
        return httpx.Response(200, text="end")

    transport, calls = transport_for(handler)
    resolver = Resolver({"example.com": [PUBLIC]})
    assert scrape.fetch("https://example.com/0", resolver=resolver, transport=transport).text == "end"
    assert len(calls) == 6


def test_six_redirects_are_stopped():
    def handler(request):
        step = int(request.url.path.strip("/") or 0)
        return httpx.Response(302, headers={"location": f"/{step + 1}"})

    transport, calls = transport_for(handler)
    resolver = Resolver({"example.com": [PUBLIC]})
    with pytest.raises(httpx.TooManyRedirects):
        scrape.fetch("https://example.com/0", resolver=resolver, transport=transport)
    assert len(calls) == 6


def test_a_3mb_body_is_cut_at_2mb():
    chunk = b"a" * 65536

    def body():
        for _ in range(48):  # 3 MB
            yield chunk

    transport, _ = transport_for(lambda request: httpx.Response(200, content=body()))
    resolver = Resolver({"example.com": [PUBLIC]})
    response = scrape.fetch("https://example.com", resolver=resolver, transport=transport)
    assert len(response.text) == scrape.MAX_BODY_BYTES == 2 * 1024 * 1024


def test_resolution_failure_is_treated_as_unreachable():
    transport, calls = transport_for(ok)
    with pytest.raises(httpx.ConnectError):
        scrape.fetch("https://nowhere.example.com", resolver=Resolver(), transport=transport)
    assert calls == []


def test_get_description_reports_the_refusal_and_makes_no_request(monkeypatch):
    transport, calls = transport_for(ok)
    monkeypatch.setattr(scrape, "DEFAULT_TRANSPORT", transport)
    site = scrape.get_description("http://127.0.0.1")
    assert site["error"] == REFUSED
    assert calls == []


def test_get_description_refuses_localhost_style_names_with_no_dot(monkeypatch):
    transport, calls = transport_for(ok)
    monkeypatch.setattr(scrape, "DEFAULT_TRANSPORT", transport)
    site = scrape.get_description("localhost:8000")
    assert site["error"] == REFUSED
    assert calls == []


def test_get_description_refuses_a_redirect_to_a_private_host(monkeypatch):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://10.0.0.5/"})

    transport, calls = transport_for(handler)
    monkeypatch.setattr(scrape, "DEFAULT_TRANSPORT", transport)
    monkeypatch.setattr(scrape, "resolve_host", Resolver({"example.com": [PUBLIC]}))
    site = scrape.get_description("example.com")
    assert site["error"] == REFUSED
    assert calls == ["https://example.com"]


def test_about_page_on_a_private_address_is_not_fetched(monkeypatch):
    transport, calls = transport_for(ok)
    monkeypatch.setattr(scrape, "DEFAULT_TRANSPORT", transport)
    monkeypatch.setattr(scrape, "resolve_host", Resolver({"example.com": [PUBLIC]}))
    assert scrape.get_about_text("http://169.254.169.254/about") is None
    assert scrape.get_careers_text("http://10.0.0.5/careers") is None
    assert scrape.get_customers_text("http://localhost/customers") is None
    assert calls == []
