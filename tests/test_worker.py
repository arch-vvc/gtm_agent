import worker
from enrich import Company


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    """Stands in for psycopg.connect(...): a context manager that records SQL."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return FakeCursor(self.rows.pop(0))


def use_fake_connection(monkeypatch, rows):
    conn = FakeConnection(rows)
    monkeypatch.setattr(worker.psycopg, "connect", lambda *args, **kwargs: conn)
    return conn


RESULT = {
    "name": "Stripe",
    "company": Company(industry="Fintech", what_they_sell="Payment APIs", target_customer="Online businesses"),
    "model": "fake-model",
    "error": None,
}


def test_save_inserts_and_returns_new_id(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(7,)])

    assert worker.save("https://stripe.com", RESULT) == 7

    sql, params = conn.calls[0]
    assert "INSERT INTO companies" in sql
    assert params == ("https://stripe.com", "Stripe", "Fintech", "Payment APIs", "Online businesses", "fake-model", None)


def test_save_returns_existing_id_when_url_already_saved(monkeypatch):
    # First query (INSERT ... ON CONFLICT DO NOTHING) returns no row, then the lookup finds id 3.
    conn = use_fake_connection(monkeypatch, [None, (3,)])

    assert worker.save("https://stripe.com", RESULT) == 3

    assert "INSERT INTO companies" in conn.calls[0][0]
    assert "SELECT id FROM companies" in conn.calls[1][0]
    assert conn.calls[1][1] == ("https://stripe.com",)


def test_save_stores_nulls_when_there_is_no_company(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(1,)])
    failed = {"name": "Example", "company": None, "model": None, "error": "Could not reach site"}

    assert worker.save("https://example.com", failed) == 1

    assert conn.calls[0][1] == ("https://example.com", "Example", None, None, None, None, "Could not reach site")
