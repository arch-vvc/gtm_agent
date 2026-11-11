from fastapi.testclient import TestClient

import main

NOTE = "Stripe fits.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]"
TAILORING = ["Use card sample data", "Name personas after merchants", "Say payouts"]

PITCH_ROW = {
    "id": 1,
    "url": "https://stripe.com",
    "name": "Stripe",
    "cluster": "F",
    "demo": "none built",
    "pitch_note": NOTE,
    "pitch_error": None,
    "tailoring": TAILORING,
    "hiring_fde": True,
}

OLD_ROW = {
    "id": 2,
    "url": "https://old.example",
    "name": "Old",
    "industry": "Fintech",
    "cluster": None,
    "demo": None,
    "pitch_note": None,
    "pitch_error": None,
    "tailoring": None,
    "hiring_fde": None,
}


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    """Stands in for psycopg.connect(...): a context manager that returns canned rows."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return FakeCursor(self.rows)


def use_rows(monkeypatch, rows):
    conn = FakeConnection(rows)
    monkeypatch.setattr(main.psycopg, "connect", lambda *args, **kwargs: conn)
    return conn


# No context manager, so the lifespan (and create_tables) never runs.
client = TestClient(main.app)


def test_pitch_returns_markdown(monkeypatch):
    use_rows(monkeypatch, [PITCH_ROW])

    response = client.get("/companies/1/pitch")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert NOTE in response.text
    for item in TAILORING:
        assert item in response.text


def test_pitch_404_unknown_company(monkeypatch):
    use_rows(monkeypatch, [])

    response = client.get("/companies/99/pitch")

    assert response.status_code == 404
    assert response.json() == {"detail": "Company not found"}


def test_pitch_404_null_note_with_pitch_error(monkeypatch):
    row = dict(PITCH_ROW, pitch_note=None, pitch_error="names not found on the site: Zorbo")
    use_rows(monkeypatch, [row])

    response = client.get("/companies/1/pitch")

    assert response.status_code == 404
    assert response.json() == {"detail": "No pitch for this company: names not found on the site: Zorbo"}


def test_pitch_404_old_row_without_pitch_fields(monkeypatch):
    use_rows(monkeypatch, [OLD_ROW])

    response = client.get("/companies/2/pitch")

    assert response.status_code == 404
    assert response.json() == {"detail": "No pitch for this company: it was enriched before the pitch engine existed"}


def test_get_companies_ok_with_null_new_columns(monkeypatch):
    use_rows(monkeypatch, [OLD_ROW, PITCH_ROW])

    response = client.get("/companies")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["pitch_note"] is None
    assert body[0]["tailoring"] is None
    assert body[0]["hiring_fde"] is None
    assert body[1]["tailoring"] == TAILORING


def test_create_tables_runs_the_whole_schema_in_one_execute(monkeypatch):
    conn = use_rows(monkeypatch, [])

    main.create_tables()

    assert conn.calls == [(main.SCHEMA_FILE.read_text(), ())]
    assert "ADD COLUMN IF NOT EXISTS pitch_note" in conn.calls[0][0]
