import pytest

from scripts import merge_duplicates
from scripts.merge_duplicates import (
    Row,
    choose_survivor,
    find_groups,
    plan_merges,
)


def make_row(row_id, url, name, domain=None, industry="Software", what="Workspace app", target="Teams"):
    return Row(row_id, url, name, domain, industry, what, target, None)


NOTION_COM = make_row(3, "https://notion.com", "Notion", "notion.com")
NOTION_SO = make_row(7, "https://notion.so", "notion")
STRIPE = make_row(4, "https://stripe.com", "Stripe", "stripe.com")


# ---- pure functions ----


def test_find_groups_links_rows_with_the_same_name_ignoring_case():
    groups = find_groups([NOTION_COM, STRIPE, NOTION_SO])

    assert len(groups) == 1
    assert [row.id for row in groups[0].rows] == [3, 7]
    assert groups[0].reasons == [("name", "notion")]


def test_find_groups_links_rows_with_the_same_domain():
    first = make_row(1, "https://a.com", "Alpha", "Shared.com")
    second = make_row(2, "https://b.com", "Beta", "shared.COM")

    groups = find_groups([first, second])

    assert [row.id for row in groups[0].rows] == [1, 2]
    assert groups[0].reasons == [("domain", "shared.com")]


def test_find_groups_follows_a_chain_of_name_and_domain_links():
    # 1 and 2 share a domain, 2 and 3 share a name, 3 and 4 share a domain.
    rows = [
        make_row(1, "https://one.com", "Uno", "shared.com"),
        make_row(2, "https://two.com", "Chain", "shared.com"),
        make_row(3, "https://three.com", "chain", "other.com"),
        make_row(4, "https://four.com", "Quattro", "OTHER.com"),
        make_row(5, "https://five.com", "Alone", "alone.com"),
    ]

    groups = find_groups(rows)

    assert len(groups) == 1
    assert [row.id for row in groups[0].rows] == [1, 2, 3, 4]
    assert groups[0].reasons == [("domain", "other.com"), ("domain", "shared.com"), ("name", "chain")]


def test_find_groups_never_links_rows_on_empty_names_or_domains():
    rows = [
        make_row(1, "https://a.com", None, None),
        make_row(2, "https://b.com", "", ""),
        make_row(3, "https://c.com", "  ", "  "),
    ]

    assert find_groups(rows) == []


def test_find_groups_returns_nothing_when_there_are_no_duplicates():
    assert find_groups([NOTION_COM, STRIPE]) == []


def test_choose_survivor_is_the_lowest_id_with_no_junk_answers():
    junk_low = make_row(1, "https://notion.so", "Notion", target="Not available")
    good_mid = make_row(5, "https://notion.com", "Notion")
    good_high = make_row(9, "https://www.notion.com", "Notion")

    assert choose_survivor([junk_low, good_high, good_mid]).id == 5


def test_choose_survivor_falls_back_to_the_lowest_id_when_every_row_is_junk():
    first = make_row(8, "https://a.com", "A", industry="N/A")
    second = make_row(2, "https://b.com", "A", what="unknown")

    assert choose_survivor([first, second]).id == 2


def test_plan_merges_sets_the_survivor_domain_from_a_loser_when_it_has_none():
    survivor = make_row(1, "https://notion.so", "Notion", None)
    loser = make_row(2, "https://notion.com", "notion", "Notion.com")

    plan = plan_merges([survivor, loser])

    assert len(plan) == 1
    assert plan[0].survivor.id == 1
    assert [row.id for row in plan[0].losers] == [2]
    assert plan[0].set_domain == "Notion.com"


def test_plan_merges_keeps_the_survivor_domain_when_it_has_one():
    plan = plan_merges([NOTION_COM, make_row(7, "https://notion.so", "notion", "notion.so")])

    assert plan[0].survivor.id == 3
    assert plan[0].set_domain is None


# ---- fake connection ----


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    """Stands in for psycopg.connect(...): records every execute and how the transaction ended."""

    def __init__(self, rows, fail_on=None):
        self.rows = rows
        self.fail_on = fail_on
        self.calls = []
        self.ended = None
        self.read_only = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.ended = "rollback" if exc_type else "commit"
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if self.fail_on and sql.startswith(self.fail_on):
            raise RuntimeError("boom")
        return FakeCursor(self.rows)

    def writes(self):
        return [(sql, params) for sql, params in self.calls if sql.startswith(("UPDATE", "DELETE", "INSERT"))]


def to_tuple(row):
    return (row.id, row.url, row.name, row.domain, row.industry, row.what_they_sell, row.target_customer, row.created_at)


def run_main(monkeypatch, rows, argv=(), fail_on=None):
    conn = FakeConnection([to_tuple(row) for row in rows], fail_on=fail_on)
    monkeypatch.setenv("DB_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setattr(merge_duplicates.psycopg, "connect", lambda *args, **kwargs: conn)
    return conn, merge_duplicates.main(list(argv))


# ---- main ----


def test_dry_run_prints_the_keep_and_merge_lines_and_writes_nothing(monkeypatch, capsys):
    conn, code = run_main(monkeypatch, [NOTION_COM, NOTION_SO, STRIPE])

    out = capsys.readouterr().out
    assert code == 0
    assert "Group 1 (matched by name 'notion'): keep id 3 https://notion.com, merge id 7 https://notion.so" in out
    assert "DRY RUN. Nothing was changed. Re-run with --apply to merge 1 rows." in out
    assert conn.writes() == []
    assert not any(sql.startswith(("UPDATE", "DELETE")) for sql, _ in conn.calls)
    assert conn.read_only is True


def test_dry_run_reports_a_domain_to_be_set(monkeypatch, capsys):
    survivor = make_row(1, "https://notion.so", "Notion", None)
    loser = make_row(2, "https://notion.com", "notion", "notion.com")

    conn, code = run_main(monkeypatch, [survivor, loser])

    out = capsys.readouterr().out
    assert code == 0
    assert "keep id 1 https://notion.so, merge id 2 https://notion.com" in out
    assert "set domain of id 1 to notion.com" in out
    assert conn.writes() == []


def test_nothing_to_merge_prints_a_message_and_writes_nothing(monkeypatch, capsys):
    conn, code = run_main(monkeypatch, [NOTION_COM, STRIPE])

    assert code == 0
    assert "Nothing to merge." in capsys.readouterr().out
    assert conn.writes() == []

    conn, code = run_main(monkeypatch, [NOTION_COM, STRIPE], argv=["--apply"])
    assert code == 0
    assert conn.writes() == []


def test_apply_issues_the_planned_writes_in_one_transaction(monkeypatch, capsys):
    survivor = make_row(1, "https://notion.so", "Notion", None)
    loser = make_row(2, "https://notion.com", "notion", "notion.com")
    other_survivor = make_row(10, "https://acme.com", "Acme", "acme.com")
    other_loser = make_row(11, "https://acme.io", "ACME", None)

    conn, code = run_main(monkeypatch, [survivor, loser, other_survivor, other_loser], argv=["--apply"])

    out = capsys.readouterr().out
    assert code == 0
    assert conn.writes() == [
        (merge_duplicates.UPDATE_DOMAIN, ("notion.com", 1)),
        (merge_duplicates.REMOVE_LOSERS, ([2],)),
        (merge_duplicates.REMOVE_LOSERS, ([11],)),
    ]
    assert conn.ended == "commit"
    assert conn.read_only is False
    assert "Merged 2 rows into 2 kept rows." in out


def test_apply_sql_is_parameterised(monkeypatch):
    conn, _ = run_main(monkeypatch, [NOTION_COM, NOTION_SO], argv=["--apply"])

    for sql, params in conn.writes():
        assert "%s" in sql
        assert "notion" not in sql.lower()
        assert params


def test_apply_rolls_back_and_exits_non_zero_when_a_write_fails(monkeypatch, capsys):
    conn, code = run_main(monkeypatch, [NOTION_COM, NOTION_SO], argv=["--apply"], fail_on="DELETE")

    assert code == 1
    assert conn.ended == "rollback"
    assert "boom" in capsys.readouterr().err


def test_missing_db_url_gives_a_clear_error_and_a_non_zero_exit(monkeypatch, capsys):
    monkeypatch.delenv("DB_URL", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("must not connect without DB_URL")

    monkeypatch.setattr(merge_duplicates.psycopg, "connect", fail_if_called)

    assert merge_duplicates.main([]) == 2
    assert "DB_URL is not set" in capsys.readouterr().err


def test_unknown_flag_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_URL", "postgresql://test:test@localhost:5432/test")

    with pytest.raises(SystemExit) as stopped:
        merge_duplicates.main(["--yes"])

    assert stopped.value.code != 0
