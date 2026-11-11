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


class StopLoop(Exception):
    """Raised by the fake redis to leave the worker's infinite loop after one job."""


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.steps = []

    def hset(self, key, mapping):
        self.steps.append(lambda: self.redis.hashes.setdefault(key, {}).update(mapping))

    def expire(self, key, seconds):
        pass

    def execute(self):
        for step in self.steps:
            step()


class FakeRedis:
    """Hands out one job, then raises StopLoop on the next brpop."""

    def __init__(self, url):
        self.hashes = {"job:j1": {"url": url, "status": "queued"}}
        self.popped = False

    def scan_iter(self, match):
        return iter([])

    def hget(self, key, field):
        return self.hashes[key].get(field)

    def hset(self, key, field, value):
        self.hashes[key][field] = value

    def pipeline(self):
        return FakePipeline(self)

    def brpop(self, name, timeout):
        if self.popped:
            raise StopLoop
        self.popped = True
        return name, "j1"


def run_one_job(monkeypatch, enrich_result):
    fake = FakeRedis("https://canva.com")
    saved = []
    monkeypatch.setattr(worker, "r", fake)
    monkeypatch.setattr(worker, "find_company", lambda url: None)
    monkeypatch.setattr(worker, "enrich", lambda url: enrich_result)
    monkeypatch.setattr(worker, "save", lambda url, result: saved.append(result) or 9)

    with pytest.raises(StopLoop):
        worker.main()

    return fake.hashes["job:j1"], saved


def test_main_marks_job_failed_and_does_not_save_when_enrich_returns_an_error(monkeypatch):
    error = "The model could not fill in industry from the site text (it answered 'Not available')."
    failed = {"name": "Canva", "company": None, "model": None, "error": error}

    job, saved = run_one_job(monkeypatch, failed)

    assert job["status"] == "failed"
    assert job["error"] == error
    assert saved == []


def test_main_saves_job_when_enrich_succeeds(monkeypatch):
    job, saved = run_one_job(monkeypatch, RESULT)

    assert job["status"] == "done"
    assert job["company_id"] == 9
    assert saved == [RESULT]
