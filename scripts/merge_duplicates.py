"""Merge duplicate rows in the companies table.

Run it from the repo root. The default is a dry run that only prints the plan:

    DB_URL=postgresql://... python -m scripts.merge_duplicates
    DB_URL=postgresql://... python -m scripts.merge_duplicates --apply

Two rows are duplicates when they share the same non empty domain, or the same
non empty name, ignoring case. Rows linked through a chain of such matches end
up in one group. In each group one row is kept and the others are removed.
"""

import argparse
import os
import sys
from dataclasses import dataclass

import psycopg

from junk import junk_fields

SELECT_ROWS="SELECT id, url, name, domain, industry, what_they_sell, target_customer, created_at FROM companies ORDER BY id"
UPDATE_DOMAIN="UPDATE companies SET domain = %s WHERE id = %s"
REMOVE_LOSERS="DELETE FROM companies WHERE id = ANY(%s)"


@dataclass
class Row:
    id: int
    url: str
    name: str | None
    domain: str | None
    industry: str | None
    what_they_sell: str | None
    target_customer: str | None
    created_at: object = None


@dataclass
class Group:
    rows: list  # sorted by id
    reasons: list  # for example [("name", "notion")]


@dataclass
class Merge:
    survivor: Row
    losers: list
    reasons: list
    set_domain: str | None = None


def clean(value):
    return (value or "").strip().lower()


def find_groups(rows):
    """Group rows that share a non empty domain or a non empty name, ignoring case."""
    parent={row.id: row.id for row in rows}

    def root(row_id):
        while parent[row_id] != row_id:
            parent[row_id]=parent[parent[row_id]]
            row_id=parent[row_id]
        return row_id

    owner_of_key={}
    members_of_key={}
    for row in rows:
        for kind, value in (("domain", clean(row.domain)), ("name", clean(row.name))):
            if not value:
                continue
            key=(kind, value)
            members_of_key.setdefault(key, []).append(row.id)
            if key in owner_of_key:
                parent[root(row.id)]=root(owner_of_key[key])
            else:
                owner_of_key[key]=row.id

    by_root={}
    for row in rows:
        by_root.setdefault(root(row.id), []).append(row)

    groups=[]
    for members in by_root.values():
        if len(members) < 2:
            continue
        members=sorted(members, key=lambda row: row.id)
        member_ids={row.id for row in members}
        # A key shared by two or more rows always lands in exactly one group.
        reasons=[key for key, ids in members_of_key.items() if len(ids) > 1 and ids[0] in member_ids]
        reasons.sort(key=lambda key: (key[0] != "domain", key[1]))
        groups.append(Group(rows=members, reasons=reasons))
    return sorted(groups, key=lambda group: group.rows[0].id)


def choose_survivor(rows):
    """Lowest id among rows with no junk answers, or the lowest id overall if every row is junk."""
    good=[row for row in rows if not junk_fields(row)]
    return min(good or rows, key=lambda row: row.id)


def plan_merges(rows):
    merges=[]
    for group in find_groups(rows):
        survivor=choose_survivor(group.rows)
        losers=[row for row in group.rows if row.id != survivor.id]
        set_domain=None
        if not clean(survivor.domain):
            donor=next((row for row in losers if clean(row.domain)), None)
            if donor:
                set_domain=donor.domain.strip()
        merges.append(Merge(survivor=survivor, losers=losers, reasons=group.reasons, set_domain=set_domain))
    return merges


def describe_reasons(reasons):
    return " and ".join(f"{kind} '{value}'" for kind, value in reasons)


def describe_merge(number, merge):
    parts=[f"keep id {merge.survivor.id} {merge.survivor.url}"]
    parts+=[f"merge id {loser.id} {loser.url}" for loser in merge.losers]
    line=f"Group {number} (matched by {describe_reasons(merge.reasons)}): " + ", ".join(parts)
    if merge.set_domain:
        line+=f" (will set domain of id {merge.survivor.id} to {merge.set_domain})"
    return line


def count_losers(merges):
    return sum(len(merge.losers) for merge in merges)


def load_rows(conn):
    return [Row(*values) for values in conn.execute(SELECT_ROWS).fetchall()]


def apply_merges(conn, merges):
    for merge in merges:
        if merge.set_domain:
            conn.execute(UPDATE_DOMAIN, (merge.set_domain, merge.survivor.id))
        conn.execute(REMOVE_LOSERS, ([loser.id for loser in merge.losers],))


def main(argv=None):
    parser=argparse.ArgumentParser(description="Merge duplicate rows in the companies table. Dry run unless --apply is given.")
    parser.add_argument("--apply", action="store_true", help="really merge the rows (default is a dry run)")
    args=parser.parse_args(argv)

    db_url=os.environ.get("DB_URL")
    if not db_url:
        print("DB_URL is not set. Run it like: DB_URL=postgresql://user:pass@host:5432/dbname python -m scripts.merge_duplicates", file=sys.stderr)
        return 2

    try:
        # One connection, one transaction: it commits when the with block ends
        # and rolls back if anything raised. A dry run opens it read only.
        with psycopg.connect(db_url) as conn:
            if not args.apply:
                conn.read_only=True
            merges=plan_merges(load_rows(conn))
            if merges and args.apply:
                apply_merges(conn, merges)
    except Exception as e:  # noqa: BLE001 (any failure must roll back and exit non zero)
        print(f"Error: {e}. Nothing was changed.", file=sys.stderr)
        return 1

    if not merges:
        print("Nothing to merge.")
        return 0

    for number, merge in enumerate(merges, start=1):
        print(describe_merge(number, merge))
    total=count_losers(merges)
    if args.apply:
        print(f"Merged {total} rows into {len(merges)} kept rows.")
    else:
        print(f"DRY RUN. Nothing was changed. Re-run with --apply to merge {total} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
