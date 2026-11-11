import re
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
SCHEMA_TEXT = SCHEMA.read_text()

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
    "domain": "TEXT",
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
);"""

ADD_COLUMN = "ALTER TABLE companies ADD COLUMN IF NOT EXISTS domain TEXT;"
DOMAIN_INDEX = "CREATE INDEX IF NOT EXISTS companies_domain_idx ON companies (lower(domain));"
NAME_INDEX = "CREATE INDEX IF NOT EXISTS companies_name_idx ON companies (lower(name));"


def alter_lines():
    return [
        line
        for line in SCHEMA_TEXT.splitlines()
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
    assert SCHEMA_TEXT.startswith(ORIGINAL_CREATE_TABLE + "\n")


def test_domain_column_is_added_idempotently_and_nullable():
    assert ADD_COLUMN in SCHEMA_TEXT
    domain_lines = [line for line in SCHEMA_TEXT.splitlines() if "domain" in line.lower()]
    for line in domain_lines:
        assert "NOT NULL" not in line.upper()
        assert "DEFAULT" not in line.upper()


def test_both_lookup_indexes_are_created_idempotently():
    assert DOMAIN_INDEX in SCHEMA_TEXT
    assert NAME_INDEX in SCHEMA_TEXT


def test_new_statements_come_after_the_create_table_block():
    table_end = SCHEMA_TEXT.index(ORIGINAL_CREATE_TABLE) + len(ORIGINAL_CREATE_TABLE)
    for statement in (ADD_COLUMN, DOMAIN_INDEX, NAME_INDEX):
        assert SCHEMA_TEXT.index(statement) > table_end
    # The index on domain needs the column to exist first.
    assert SCHEMA_TEXT.index(ADD_COLUMN) < SCHEMA_TEXT.index(DOMAIN_INDEX)


def test_every_statement_ends_with_a_semicolon_so_one_execute_can_run_the_file():
    statements = [part.strip() for part in SCHEMA_TEXT.split(";") if part.strip()]
    # The create table, ten new columns and two indexes.
    assert len(statements) == 1 + len(NEW_COLUMNS) + 2
