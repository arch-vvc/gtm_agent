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

ALTER TABLE companies ADD COLUMN IF NOT EXISTS domain TEXT;

CREATE INDEX IF NOT EXISTS companies_domain_idx ON companies (lower(domain));
CREATE INDEX IF NOT EXISTS companies_name_idx ON companies (lower(name));
