import re
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

# Column name and type of every column added after the first release.
NEW_COLUMNS = {
    "cluster": "TEXT",
    "cluster_reason": "TEXT",
    "demo": "TEXT",
    "customer_pain": "TEXT",
    "tailoring": "TEXT[]",
    "pitch_note": "TEXT",
    "pitch_error": "TEXT",
    "careers_url": "TEXT",
    "hiring_fde": "BOOLEAN",
}

ORIGINAL_CREATE_TABLE = """CREATE TABLE IF NOT EXISTS companies (
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


def alter_lines():
    return [
        line
        for line in SCHEMA.read_text().splitlines()
        if line.upper().startswith("ALTER TABLE")
    ]


def test_schema_adds_every_new_column_idempotently():
    lines = alter_lines()
    for column, sql_type in NEW_COLUMNS.items():
        expected = (
            f"ALTER TABLE companies ADD COLUMN IF NOT EXISTS {column} {sql_type};"
        )
        assert expected in lines, f"missing: {expected}"
    assert len(lines) == len(NEW_COLUMNS)


def test_schema_new_columns_are_nullable():
    for line in alter_lines():
        assert not re.search(r"NOT\s+NULL", line, re.IGNORECASE), line
        assert not re.search(r"\bDEFAULT\b", line, re.IGNORECASE), line


def test_schema_create_table_block_unchanged():
    assert SCHEMA.read_text().startswith(ORIGINAL_CREATE_TABLE)
