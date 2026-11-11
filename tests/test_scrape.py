import pytest

from scrape import normalise_url


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
