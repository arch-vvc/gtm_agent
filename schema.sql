CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    name TEXT,
    industry TEXT,
    what_they_sell TEXT,
    target_customer TEXT,
    model TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
