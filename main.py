from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row
from enrich import enrich
from scape import normalise_url
import psycopg
import os

app=FastAPI()
DB_URL=os.environ["DB_URL"]


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

    result=enrich(url)
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
    return {"status": "created", "id": row[0], **result}


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