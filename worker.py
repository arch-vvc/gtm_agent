import os
import traceback

import psycopg
import redis

from enrich import enrich

DB_URL=os.environ["DB_URL"]
REDIS_HOST=os.environ.get("REDIS_HOST", "redis")
r=redis.Redis(host=REDIS_HOST, decode_responses=True, socket_timeout=30)
JOB_TTL=24*60*60


def finish(key, fields):
    pipe=r.pipeline()
    pipe.hset(key, mapping=fields)
    pipe.expire(key, JOB_TTL)
    pipe.execute()


def save(url, result):
    company=result["company"]
    with psycopg.connect(DB_URL) as conn:
        row=conn.execute(
            "INSERT INTO companies (url, name, domain, industry, what_they_sell, target_customer, model, error, cluster, cluster_reason, demo, customer_pain, tailoring, pitch_note, pitch_error, careers_url, hiring_fde) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING RETURNING id",
            (
                url,
                result["name"],
                result.get("domain"),
                company.industry if company else None,
                company.what_they_sell if company else None,
                company.target_customer if company else None,
                result["model"],
                result["error"],
                company.cluster if company else None,
                company.cluster_reason if company else None,
                result.get("demo"),
                company.customer_pain if company else None,
                list(company.tailoring) if company else None,
                # From result, not company: the guard sets result["pitch_note"] to None when it rejects a note.
                result.get("pitch_note"),
                result.get("pitch_error"),
                result.get("careers_url"),
                result.get("hiring_fde"),
            ),
        ).fetchone()
    if row is None:
        return find_company(url)
    return row[0]


def find_company(url):
    with psycopg.connect(DB_URL) as conn:
        row=conn.execute(
            "SELECT id FROM companies WHERE url=%s",
            (url,),
        ).fetchone()
    return row[0] if row else None


def find_duplicate(domain, name):
    """Return (company_id, matched_by) for a saved company with the same domain or name, else None.

    matched_by is "domain" or "name". A domain match wins over a name match,
    then the lowest id. An empty domain or name never matches anything.
    """
    domain=(domain or "").strip() or None
    name=(name or "").strip() or None
    if domain is None and name is None:
        return None
    with psycopg.connect(DB_URL) as conn:
        row=conn.execute(
            "SELECT id, COALESCE(lower(domain) = lower(%s::text), false) FROM companies "
            "WHERE lower(domain) = lower(%s::text) OR lower(name) = lower(%s::text) "
            "ORDER BY 2 DESC, id LIMIT 1",
            (domain, domain, name),
        ).fetchone()
    if row is None:
        return None
    return row[0], "domain" if row[1] else "name"


def main():
    for stuck_key in r.scan_iter(match="job:*"):
        if r.hget(stuck_key, "status") == "running":
            finish(stuck_key, {"status": "failed", "error": "Worker restarted mid job, please retry"})
            print(f"Marked {stuck_key} as failed, it was left running")

    print("Worker started, waiting for jobs")
    while True:
        popped=r.brpop("jobs", timeout=5)
        if popped is None:
            continue
        _, job_id=popped
        key=f"job:{job_id}"
        url=r.hget(key, "url")
        print(f"Picked up {job_id} for {url}")

        r.hset(key, "status", "running")
        try:
            existing_id=find_company(url)
            if existing_id:
                finish(key, {"status": "done", "company_id": existing_id})
                print(f"Skipped {job_id}, {url} already saved as company {existing_id}")
                continue
            result=enrich(url)
            if result.get("error"):
                finish(key, {"status": "failed", "error": result["error"]})
                print(f"Failed {job_id}: {result['error']}")
                continue
            duplicate=find_duplicate(result.get("domain"), result.get("name"))
            if duplicate:
                duplicate_id, matched_by=duplicate
                finish(key, {"status": "done", "company_id": duplicate_id, "duplicate_of": duplicate_id, "matched_by": matched_by})
                what="final domain" if matched_by == "domain" else "name"
                print(f"Skipped {job_id}, {url} was treated as a duplicate of company {duplicate_id} because of its {what}")
                continue
            company_id=save(url, result)
            finish(key, {"status": "done", "company_id": company_id})
            print(f"Finished {job_id}, saved as company {company_id}")
        except Exception as e:  # noqa: BLE001 (the loop must survive any job failure)
            finish(key, {"status": "failed", "error": str(e)})
            traceback.print_exc()


if __name__ == "__main__":
    main()
