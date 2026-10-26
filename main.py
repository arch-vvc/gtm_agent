from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row
from scape import normalise_url
from enrich import enrich
import psycopg
import os

app=FastAPI()
DB_URL=os.environ["DB_URL"]


class Leads(BaseModel):
    name: str
    industry: str
    package: int


class EnrichRequest(BaseModel):
    url: str


@app.post("/leads")
def add_leads(lead: Leads):
    with psycopg.connect(DB_URL) as conn:
        row=conn.execute(
            "INSERT INTO leads (name, industry, package) VALUES (%s, %s, %s) RETURNING id",
            (lead.name, lead.industry, lead.package),
        ).fetchone()
    return {"id": row[0], **lead.model_dump()}


@app.get("/leads/{lead_id}")
def get_leads(lead_id: int):
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        row=conn.execute("SELECT * FROM leads WHERE id=%s", (lead_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row


@app.get("/leads")
def get_all_leads():
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        rows=conn.execute("SELECT * FROM leads").fetchall()
    return rows


@app.post("/enrich")
def enrich_company(req: EnrichRequest):
    url=normalise_url(req.url)
    if url is None:
        raise HTTPException(status_code=400, detail="Invalid URL")
    result=enrich(url)
    company=result["company"]
    with psycopg.connect(DB_URL) as conn:
        row=conn.execute(
            "INSERT INTO companies (url, name, industry, what_they_sell, target_customer, error) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (
                url,
                result["name"],
                company.industry if company else None,
                company.what_they_sell if company else None,
                company.target_customer if company else None,
                result["error"],
            ),
        ).fetchone()
    return {"id": row[0], **result}