"""Check that schema.sql migrates an old companies table without losing data.

Run from the repo root with a Postgres URL in DB_URL:

    DB_URL=postgresql://user:pass@localhost:5432/dbname python -m scripts.check_migration

Everything happens inside a throwaway schema called migration_check, so a real
companies table is never touched.
"""

import os
import sys
from pathlib import Path

import psycopg

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.sql"
CHECK_SCHEMA = "migration_check"

# Exact copy of the companies table as it was before the pitch engine.
OLD_SCHEMA = """CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    name TEXT,
    industry TEXT,
    what_they_sell TEXT,
    target_customer TEXT,
    model TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Column name and the type information_schema reports for it.
NEW_COLUMNS = {
    "cluster": "text",
    "cluster_reason": "text",
    "demo": "text",
    "customer_pain": "text",
    "tailoring": "ARRAY",
    "pitch_note": "text",
    "pitch_error": "text",
    "careers_url": "text",
    "hiring_fde": "boolean",
    "domain": "text",
}

# Lookup indexes the worker relies on to find duplicates.
NEW_INDEXES = ["companies_domain_idx", "companies_name_idx"]


def check(conn):
    schema_sql = SCHEMA_FILE.read_text()

    conn.execute(f"CREATE SCHEMA {CHECK_SCHEMA}")
    conn.execute(f"SET search_path TO {CHECK_SCHEMA}")
    print(f"created throwaway schema {CHECK_SCHEMA}")

    conn.execute(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO companies (url, name) VALUES (%s, %s)",
        ("https://example.com", "Example"),
    )
    print("created old companies table and inserted one row")

    # Same call shape as create_tables() in main.py: the whole file, one execute.
    for run in (1, 2):
        conn.execute(schema_sql)
        print(f"applied schema.sql, run {run} of 2")

    rows = conn.execute("SELECT name FROM companies").fetchall()
    assert rows == [("Example",)], f"expected the old row to survive, got {rows}"
    print("old row survived")

    names = ", ".join(NEW_COLUMNS)
    row = conn.execute(f"SELECT {names} FROM companies").fetchone()
    assert all(value is None for value in row), f"new columns not NULL: {row}"
    print(f"all {len(NEW_COLUMNS)} new columns are NULL on the old row")

    found = dict(
        conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'companies'",
            (CHECK_SCHEMA,),
        ).fetchall()
    )
    for column, data_type in NEW_COLUMNS.items():
        assert found.get(column) == data_type, (
            f"column {column}: expected {data_type}, got {found.get(column)}"
        )
    print(f"all {len(NEW_COLUMNS)} new columns exist with the right types")

    indexes = {
        name
        for (name,) in conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = 'companies'",
            (CHECK_SCHEMA,),
        ).fetchall()
    }
    for index in NEW_INDEXES:
        assert index in indexes, f"index {index} is missing, found {sorted(indexes)}"
    print("both lookup indexes exist")


def main():
    db_url = os.environ.get("DB_URL")
    if not db_url:
        sys.exit("DB_URL is not set")

    try:
        with psycopg.connect(db_url, autocommit=True) as conn:
            try:
                check(conn)
            finally:
                conn.execute(f"DROP SCHEMA IF EXISTS {CHECK_SCHEMA} CASCADE")
                print(f"dropped schema {CHECK_SCHEMA}")
    except (AssertionError, psycopg.Error) as err:
        sys.exit(f"MIGRATION FAILED: {err}")

    print("MIGRATION OK")


if __name__ == "__main__":
    main()
