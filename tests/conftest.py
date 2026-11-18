import os

# enrich.py, main.py and worker.py read env and build API clients at import time.
# Force dummy values so tests never use real keys or touch a real service.
os.environ["DB_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["REDIS_HOST"] = "localhost"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["GROQ_API_KEY"] = "test-groq-key"


import pytest


@pytest.fixture(autouse=True)
def evidence_not_required_by_default(monkeypatch):
    """Most tests build notes with no evidence quotes. tests/test_claim_quotes.py turns the rule on."""
    import enrich

    monkeypatch.setattr(enrich, "REQUIRE_EVIDENCE", False, raising=False)
