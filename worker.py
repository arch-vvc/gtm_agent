from enrich import enrich
import psycopg
import redis
import traceback
import os

DB_URL=os.environ["DB_URL"]
r=redis.Redis(host="redis", decode_responses=True, socket_timeout=30)

def save(url, result):
    company=result["company"]
    with psycopg.connect(DB_URL) as conn:
        row=conn.execute(
            "INSERT INTO companies (url, name, industry, what_they_sell, target_customer, model, error) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                url,
                result["name"],
                company.industry if company else None,
                company.what_they_sell if company else None,
                company.target_customer if company else None,
                result["model"],
                result["error"],
            ),
        ).fetchone()
    return row[0]

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
        result=enrich(url)
        if result.get("error"):
            r.hset(key, mapping={"status": "failed", "error": result["error"]})
            continue
        company_id=save(url, result)
        r.hset(key, mapping={"status": "done", "company_id": company_id})
        print(f"Finished {job_id}, saved as company {company_id}")
    except Exception as e:
        r.hset(key, mapping={"status": "failed", "error": str(e)})
        traceback.print_exc()