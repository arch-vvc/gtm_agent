import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from scrape import normalise_url

DB_URL=os.environ["DB_URL"]
REDIS_HOST=os.environ.get("REDIS_HOST", "redis")
SCHEMA_FILE=Path(__file__).with_name("schema.sql")
r=redis.Redis(host=REDIS_HOST, decode_responses=True)


def create_tables():
    with psycopg.connect(DB_URL) as conn:
        conn.execute(SCHEMA_FILE.read_text())


@asynccontextmanager
async def lifespan(app):
    create_tables()
    yield


app=FastAPI(lifespan=lifespan)


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
    if "company_id" in job:
        job["company_id"]=int(job["company_id"])
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