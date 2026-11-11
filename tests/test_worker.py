import re

import pytest

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
    "company": Company(
        industry="Fintech",
        what_they_sell="Payment APIs",
        target_customer="Online businesses",
        cluster="F",
        cluster_reason="The site sells payment APIs.",
        customer_pain="Online businesses need to accept payments.",
        tailoring=["Use card sample data", "Name personas after merchants", "Say payouts"],
        pitch_note="Stripe fits.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]",
    ),
    "model": "fake-model",
    "error": None,
    "demo": "none built",
    "pitch_note": "Stripe fits.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]",
    "pitch_error": None,
    "careers_url": "https://stripe.com/jobs",
    "hiring_fde": True,
}

# The 9 new columns, in the order they appear in the INSERT.
PITCH_PARAMS = (
    "F",
    "The site sells payment APIs.",
    "none built",
    "Online businesses need to accept payments.",
    ["Use card sample data", "Name personas after merchants", "Say payouts"],
    "Stripe fits.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]",
    None,
    "https://stripe.com/jobs",
    True,
)


def test_save_inserts_and_returns_new_id(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(7,)])

    assert worker.save("https://stripe.com", RESULT) == 7

    sql, params = conn.calls[0]
    assert "INSERT INTO companies" in sql
    assert params == ("https://stripe.com", "Stripe", "Fintech", "Payment APIs", "Online businesses", "fake-model", None) + PITCH_PARAMS


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

    assert conn.calls[0][1] == ("https://example.com", "Example", None, None, None, None, "Could not reach site") + (None,) * 9


def test_save_still_works_with_an_old_shaped_result(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(2,)])
    old = {"name": "Old", "company": None, "model": None, "error": "Could not reach site"}

    assert worker.save("https://old.example", old) == 2

    assert conn.calls[0][1][7:] == (None,) * 9


def test_save_writes_pitch_fields(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(5,)])
    guard_failed = dict(
        RESULT,
        pitch_note=None,
        pitch_error="names not found on the site: Zorbo",
        company=RESULT["company"].model_copy(update={"pitch_note": "Zorbo fits.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]"}),
    )

    worker.save("https://stripe.com", guard_failed)

    sql, params = conn.calls[0]
    columns = re.search(r"INSERT INTO companies \((.*?)\) VALUES", sql).group(1).split(", ")
    assert columns[7:] == [
        "cluster", "cluster_reason", "demo", "customer_pain", "tailoring",
        "pitch_note", "pitch_error", "careers_url", "hiring_fde",
    ]  # fmt: skip
    assert len(params) == len(columns) == sql.count("%s")
    by_column = dict(zip(columns, params, strict=True))
    assert by_column["cluster"] == "F"
    assert by_column["demo"] == "none built"
    assert isinstance(by_column["tailoring"], list)
    assert len(by_column["tailoring"]) == 3
    assert by_column["pitch_note"] is None  # from result, not from company.pitch_note
    assert by_column["pitch_error"] == "names not found on the site: Zorbo"
    assert by_column["careers_url"] == "https://stripe.com/jobs"
    assert by_column["hiring_fde"] is True


class StopLoop(BaseException):
    """Raised by the fake redis to leave worker.main() after one job."""


class FakeRedis:
    def __init__(self):
        self.popped = False
        self.hashes = {"job:j1": {"url": "https://stripe.com"}}

    def scan_iter(self, match=None):
        return []

    def brpop(self, name, timeout=0):
        if self.popped:
            raise StopLoop
        self.popped = True
        return ("jobs", "j1")

    def hget(self, key, field):
        return self.hashes[key].get(field)

    def hset(self, key, field=None, value=None, mapping=None):
        self.hashes[key].update(mapping or {field: value})

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, fake):
        self.fake = fake

    def hset(self, key, mapping):
        self.fake.hset(key, mapping=mapping)

    def expire(self, key, seconds):
        pass

    def execute(self):
        pass


def test_loop_finishes_done_when_the_guard_rejected_the_note(monkeypatch):
    fake = FakeRedis()
    guard_failed = dict(RESULT, pitch_note=None, pitch_error="note has 151 words, the limit is 150")
    saved = []
    monkeypatch.setattr(worker, "r", fake)
    monkeypatch.setattr(worker, "find_company", lambda url: None)
    monkeypatch.setattr(worker, "enrich", lambda url: guard_failed)
    monkeypatch.setattr(worker, "save", lambda url, result: saved.append(result) or 9)

    with pytest.raises(StopLoop):
        worker.main()

    assert saved == [guard_failed]
    assert fake.hashes["job:j1"]["status"] == "done"
    assert fake.hashes["job:j1"]["company_id"] == 9
