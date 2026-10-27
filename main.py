from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row
from scape import normalise_url
import psycopg
import redis
import uuid
import os

app=FastAPI()
DB_URL=os.environ["DB_URL"]
r=redis.Redis(host="redis", decode_responses=True)


class EnrichRequest(BaseModel):
    url: str


@app.post("/enrich")
def enrich_company(req: EnrichRequest):
    url=normalise_url(req.url)
    if url is None:
        raise HTTPException(status_code=400, detail="Invalid URL")

    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        existing=conn.execute("SELECT * FROM companies WHERE url=%s", (url,)).fetchone()
    if existing:
        return {"status": "already in the table", **existing}

    job_id=str(uuid.uuid4())
    r.hset(f"job:{job_id}", mapping={"status": "queued", "url": url})
    r.lpush("jobs", job_id)
    return {"status": "queued", "job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job=r.hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/companies")
def get_all_companies():
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        rows=conn.execute("SELECT * FROM companies ORDER BY id DESC").fetchall()
    return rows


@app.get("/companies/{company_id}")
def get_company(company_id: int):
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        row=conn.execute("SELECT * FROM companies WHERE id=%s", (company_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return row