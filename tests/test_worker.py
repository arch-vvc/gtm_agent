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
    "domain": "stripe.com",
    "company": Company(industry="Fintech", what_they_sell="Payment APIs", target_customer="Online businesses"),
    "model": "fake-model",
    "error": None,
}


def test_save_inserts_and_returns_new_id(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(7,)])

    assert worker.save("https://stripe.com", RESULT) == 7

    sql, params = conn.calls[0]
    assert "INSERT INTO companies" in sql
    assert params == ("https://stripe.com", "Stripe", "stripe.com", "Fintech", "Payment APIs", "Online businesses", "fake-model", None)


def test_save_returns_existing_id_when_url_already_saved(monkeypatch):
    # First query (INSERT ... ON CONFLICT DO NOTHING) returns no row, then the lookup finds id 3.
    conn = use_fake_connection(monkeypatch, [None, (3,)])

    assert worker.save("https://stripe.com", RESULT) == 3

    assert "INSERT INTO companies" in conn.calls[0][0]
    assert "SELECT id FROM companies" in conn.calls[1][0]
    assert conn.calls[1][1] == ("https://stripe.com",)


def test_save_stores_nulls_when_there_is_no_company(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(1,)])
    failed = {"name": "Example", "domain": None, "company": None, "model": None, "error": "Could not reach site"}

    assert worker.save("https://example.com", failed) == 1

    assert conn.calls[0][1] == ("https://example.com", "Example", None, None, None, None, None, "Could not reach site")


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


def run_one_job(monkeypatch, enrich_result, duplicate=None, url="https://canva.com"):
    fake = FakeRedis(url)
    saved = []
    monkeypatch.setattr(worker, "r", fake)
    monkeypatch.setattr(worker, "find_company", lambda url: None)
    monkeypatch.setattr(worker, "find_duplicate", lambda domain, name: duplicate)
    monkeypatch.setattr(worker, "enrich", lambda url: enrich_result)
    monkeypatch.setattr(worker, "save", lambda url, result: saved.append(result) or 9)

    with pytest.raises(StopLoop):
        worker.main()

    return fake.hashes["job:j1"], saved


def test_main_marks_job_failed_and_does_not_save_when_enrich_returns_an_error(monkeypatch):
    error = "The model could not fill in industry (answered 'Not available') from the site text."
    failed = {"name": "Canva", "domain": "canva.com", "company": None, "model": None, "error": error}

    job, saved = run_one_job(monkeypatch, failed)

    assert job["status"] == "failed"
    assert job["error"] == error
    assert saved == []


def test_main_saves_job_when_enrich_succeeds(monkeypatch):
    job, saved = run_one_job(monkeypatch, RESULT)

    assert job["status"] == "done"
    assert job["company_id"] == 9
    assert saved == [RESULT]


NOTION = {
    "name": "Notion",
    "domain": "notion.com",
    "company": Company(industry="Software", what_they_sell="Workspace app", target_customer="Teams"),
    "model": "fake-model",
    "error": None,
}


def test_main_treats_a_redirected_url_as_a_duplicate_and_does_not_save(monkeypatch, capsys):
    job, saved = run_one_job(monkeypatch, NOTION, duplicate=(4, "domain"), url="https://notion.so")

    assert job["status"] == "done"
    assert job["company_id"] == 4
    assert job["duplicate_of"] == 4
    assert job["matched_by"] == "domain"
    assert saved == []
    log = capsys.readouterr().out
    assert "https://notion.so was treated as a duplicate of company 4" in log
    assert "final domain" in log


def test_main_reports_a_name_match(monkeypatch, capsys):
    job, saved = run_one_job(monkeypatch, NOTION, duplicate=(2, "name"))

    assert job["status"] == "done"
    assert job["company_id"] == 2
    assert job["matched_by"] == "name"
    assert saved == []
    assert "name" in capsys.readouterr().out


def test_main_passes_the_result_domain_and_name_to_find_duplicate(monkeypatch):
    asked = []
    fake = FakeRedis("https://notion.so")
    monkeypatch.setattr(worker, "r", fake)
    monkeypatch.setattr(worker, "find_company", lambda url: None)
    monkeypatch.setattr(worker, "enrich", lambda url: NOTION)
    monkeypatch.setattr(worker, "find_duplicate", lambda domain, name: asked.append((domain, name)))
    monkeypatch.setattr(worker, "save", lambda url, result: 9)

    with pytest.raises(StopLoop):
        worker.main()

    assert asked == [("notion.com", "Notion")]


def test_main_saves_when_no_duplicate_exists(monkeypatch):
    job, saved = run_one_job(monkeypatch, NOTION, duplicate=None)

    assert job["status"] == "done"
    assert job["company_id"] == 9
    assert "duplicate_of" not in job
    assert "matched_by" not in job
    assert saved == [NOTION]


def test_main_does_not_dedupe_a_failed_result(monkeypatch):
    def fail_if_called(domain, name):
        raise AssertionError("find_duplicate must not run for a failed result")

    failed = {"name": "Notion", "domain": "notion.com", "company": None, "model": None, "error": "Site returned 503"}
    fake = FakeRedis("https://notion.so")
    monkeypatch.setattr(worker, "r", fake)
    monkeypatch.setattr(worker, "find_company", lambda url: None)
    monkeypatch.setattr(worker, "enrich", lambda url: failed)
    monkeypatch.setattr(worker, "find_duplicate", fail_if_called)

    with pytest.raises(StopLoop):
        worker.main()

    assert fake.hashes["job:j1"]["status"] == "failed"
    assert fake.hashes["job:j1"]["error"] == "Site returned 503"


# ---- find_duplicate ----


def test_find_duplicate_reports_a_domain_match(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(4, True)])

    assert worker.find_duplicate("Notion.com", "Notion") == (4, "domain")

    sql, params = conn.calls[0]
    assert "lower(domain)" in sql
    assert "lower(name)" in sql
    assert "LIMIT 1" in sql
    assert "%s" in sql
    assert "notion.com" not in sql.lower()
    assert params == ("Notion.com", "Notion.com", "Notion")


def test_find_duplicate_reports_a_name_match(monkeypatch):
    use_fake_connection(monkeypatch, [(2, False)])

    assert worker.find_duplicate("notion.com", "NOTION") == (2, "name")


def test_find_duplicate_returns_none_when_nothing_matches(monkeypatch):
    use_fake_connection(monkeypatch, [None])

    assert worker.find_duplicate("notion.com", "Notion") is None


def test_find_duplicate_prefers_domain_matches_and_the_lowest_id_in_sql(monkeypatch):
    conn = use_fake_connection(monkeypatch, [None])

    worker.find_duplicate("notion.com", "Notion")

    sql = " ".join(conn.calls[0][0].split())
    assert "ORDER BY 2 DESC, id" in sql


def test_find_duplicate_with_only_a_name_sends_null_for_the_domain(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(1, False)])

    assert worker.find_duplicate("", "Notion") == (1, "name")

    assert conn.calls[0][1] == (None, None, "Notion")


def test_find_duplicate_with_only_a_domain_sends_null_for_the_name(monkeypatch):
    conn = use_fake_connection(monkeypatch, [(1, True)])

    assert worker.find_duplicate("notion.com", None) == (1, "domain")

    assert conn.calls[0][1] == ("notion.com", "notion.com", None)


@pytest.mark.parametrize("domain, name", [("", ""), (None, None), ("  ", " "), (None, "")])
def test_find_duplicate_never_matches_on_empty_values(monkeypatch, domain, name):
    conn = use_fake_connection(monkeypatch, [])

    assert worker.find_duplicate(domain, name) is None

    assert conn.calls == []


def test_subdomains_of_different_companies_no_longer_match_by_name(monkeypatch):
    # Both hosts used to be named "Blog". The names now differ, so the name lookup cannot join them.
    import scrape

    stripe = scrape.name_from_host("blog.stripe.com")
    vercel = scrape.name_from_host("blog.vercel.com")
    assert stripe != vercel

    # The fake table holds only the saved blog.stripe.com row, which matches on lower(name).
    saved = {"domain": "blog.stripe.com", "name": stripe.lower()}

    def lookup(sql, params):
        domain, _, name = params
        if domain and domain.lower() == saved["domain"]:
            return (1, True)
        if name and name.lower() == saved["name"]:
            return (1, False)
        return None

    class LookupConnection(FakeConnection):
        def execute(self, sql, params=()):
            self.calls.append((sql, params))
            return FakeCursor(lookup(sql, params))

    conn = LookupConnection([])
    monkeypatch.setattr(worker.psycopg, "connect", lambda *args, **kwargs: conn)

    assert worker.find_duplicate("blog.stripe.com", stripe) == (1, "domain")
    assert worker.find_duplicate("blog.vercel.com", vercel) is None
