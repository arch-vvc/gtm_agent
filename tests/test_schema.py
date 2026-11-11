from pathlib import Path

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()

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


def test_original_create_table_block_is_unchanged():
    assert SCHEMA.startswith(ORIGINAL_CREATE_TABLE)


def test_domain_column_is_added_idempotently_and_nullable():
    assert ADD_COLUMN in SCHEMA
    domain_lines = [line for line in SCHEMA.splitlines() if "domain" in line.lower()]
    for line in domain_lines:
        assert "NOT NULL" not in line.upper()
        assert "DEFAULT" not in line.upper()


def test_both_lookup_indexes_are_created_idempotently():
    assert DOMAIN_INDEX in SCHEMA
    assert NAME_INDEX in SCHEMA


def test_new_statements_come_after_the_create_table_block():
    table_end = SCHEMA.index(ORIGINAL_CREATE_TABLE) + len(ORIGINAL_CREATE_TABLE)
    for statement in (ADD_COLUMN, DOMAIN_INDEX, NAME_INDEX):
        assert SCHEMA.index(statement) > table_end
    # The index on domain needs the column to exist first.
    assert SCHEMA.index(ADD_COLUMN) < SCHEMA.index(DOMAIN_INDEX)


def test_every_statement_ends_with_a_semicolon_so_one_execute_can_run_the_file():
    statements = [part.strip() for part in SCHEMA.split(";") if part.strip()]
    assert len(statements) == 4
