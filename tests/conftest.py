import os

# enrich.py, main.py and worker.py read env and build API clients at import time.
# Force dummy values so tests never use real keys or touch a real service.
os.environ["DB_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["REDIS_HOST"] = "localhost"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["GROQ_API_KEY"] = "test-groq-key"
