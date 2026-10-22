from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row
import psycopg

app = FastAPI()
DB_URL="postgresql://postgres:secret@localhost:5432/gtm"

class Leads(BaseModel):
    name: str
    industry: str
    package: int

@app.post("/leads")
def add_leads(lead: Leads):
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            "INSERT INTO leads (name, industry, package) VALUES (%s, %s, %s) RETURNING id",
            (lead.name, lead.industry, lead.package),
        ).fetchone()
    return {"id": row[0], **lead.model_dump()}

@app.get("/leads/{lead_id}")
def get_leads(lead_id: int):
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        row=conn.execute(
            "SELECT * FROM leads WHERE id=%s", (lead_id,)).fetchone()
    if row is None:
         raise HTTPException(status_code=404, detail="Lead not found")
    return row

@app.get("/leads")
def get_all_leads():
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
            rows=conn.execute(
                "SELECT * FROM leads"
            ).fetchall()
    return rows