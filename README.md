# gtm_agent

Give it a company website and it returns the company's industry, what they sell and who they sell to.

## Run it in 5 minutes

You need Docker with Compose, a Gemini API key and a Groq API key (both have free tiers).

```bash
git clone https://github.com/arch-vvc/gtm_agent
cd gtm_agent
cp .env.example .env
```

Open `.env` and replace the two placeholder keys with your own. Leave `DB_URL` and `REDIS_HOST` as they are, they point at the containers below.

```bash
docker compose up -d --build
```

This starts Postgres, Redis, the API on http://localhost:8000 and a background worker. The API creates the `companies` table on startup, so there is no manual database step.

Try it:

```bash
curl -X POST localhost:8000/enrich -H 'content-type: application/json' -d '{"url":"stripe.com"}'
```

Copy the `job_id` from the response and poll it until `status` is `done`:

```bash
curl localhost:8000/jobs/<job_id>
```

Useful commands: `docker compose logs app worker` to see output, `docker compose down` to stop (data is kept in the `gtm_pgdata` volume).

## API

### POST /enrich

Request:

```json
{"url": "stripe.com"}
```

Response (the job is queued, nothing is scraped yet):

```json
{"status": "queued", "job_id": "de239879-e70b-4fd2-a827-b579327d12f6"}
```

The URL is normalised first (`https` forced, `www.` and trailing slash removed, lowercased, query string dropped), so `https://www.Stripe.com/` and `stripe.com` are the same company. A URL with no dot in the host returns `400 {"detail": "Invalid URL"}`.

If that URL was already enriched, you get the saved row straight away instead of a job:

```json
{"status": "already in the table", "id": 1, "url": "https://stripe.com", "name": "Stripe", "industry": "...", "what_they_sell": "...", "target_customer": "...", "model": "...", "error": null, "created_at": "..."}
```

### GET /jobs/{job_id}

While waiting:

```json
{"status": "queued", "url": "https://stripe.com"}
```

`status` moves from `queued` to `running` to `done` or `failed`. When done:

```json
{"status": "done", "url": "https://stripe.com", "company_id": 1}
```

When failed, the reason is in `error`:

```json
{"status": "failed", "url": "https://stripe.com", "error": "All models are currently busy, please retry in a minute."}
```

If the URL turns out to be a duplicate of a company that is already saved, the job is still `done`, nothing new is saved, and the job carries two extra fields:

```json
{"status": "done", "url": "https://notion.so", "company_id": 4, "duplicate_of": 4, "matched_by": "domain"}
```

`duplicate_of` is the id of the existing row (the same as `company_id`). `matched_by` is `domain` or `name`, see "Duplicates" below.

An unknown or expired job id returns `404`.

### GET /companies/{company_id} and GET /companies

Fetch the result using the `company_id` from a finished job. `GET /companies` lists everything, newest first. The values below are illustrative, the real text comes from the model:

```json
{
  "id": 1,
  "url": "https://stripe.com",
  "name": "Stripe",
  "domain": "stripe.com",
  "industry": "Financial technology",
  "what_they_sell": "Payment processing APIs and billing software",
  "target_customer": "Online businesses and platforms of any size",
  "model": "gemini-3.5-flash",
  "error": null,
  "created_at": "2026-11-11T06:46:21.337804+00:00"
}
```

## Answer quality and duplicates

### Placeholder answers fail the job

If the model answers `Not available`, `N/A`, `Unknown`, `None` or similar for `industry`, `what_they_sell` or `target_customer`, the job is marked `failed` and nothing is saved. The error names each field and what the model said, for example:

```json
{"status": "failed", "url": "https://example.com", "error": "The model could not fill in target_customer (answered 'Not available') from the site text. The site gave too little to go on, please check the site manually."}
```

Real answers that only contain such a word, such as `None of the above insurance`, are kept.

### Customers page

When the home page links to a customers page (`/customers`, `/case-studies`, `/use-cases` and close variants, or a link with that visible text), the scraper reads it too: its headings, longer paragraphs and the alt text of customer logos, up to 2000 characters. The model is told to base `target_customer` on it, so the answer names a buyer such as "product and engineering teams at larger companies" instead of "users". Login, help and jobs links are ignored, and only links on the same site are followed. If that page cannot be fetched the job carries on without it.

### Duplicates

The same company used to be saved twice, for example `notion.com` and `notion.so` (which redirects to `notion.com`). Now, after the model has answered and before anything is saved, the worker looks for an existing row that matches either way:

- **Final domain.** The host the site ends up on after redirects, lowercased, with `www.` removed. It is stored in the new `domain` column.
- **Name, ignoring case.** The name is the main domain label of the input host, so subdomains are fine: `notion.so` gives `Notion`, `blog.stripe.com` gives `Stripe`, `shop.example.co.uk` gives `Example`.

If a row matches, the job finishes as `done` with that row's `company_id`, plus `duplicate_of` and `matched_by` (`domain` or `name`), and no new row is written. A domain match is preferred over a name match, then the lowest id. The worker log says which company the URL was treated as a duplicate of and why. A job that failed is never treated as a duplicate.

Honest limits:

- Two different companies on different TLDs that share a main label, such as `apple.com` and `apple.fr`, are treated as one company.
- Hosting platforms collapse, because a URL with a path dedupes on the domain: `github.com/openai` and `github.com/anthropic` count as the same company, and so do paths on `linkedin.com` or `medium.com`.
- The enrich call (and its LLM cost) runs before the duplicate check, so a duplicate still costs one model call.
- Rows saved before this change keep the name they were saved with, which could be a subdomain label such as `Blog`.

If this matters to you, check the `matched_by` field and look at `duplicate_of`.

The `domain` column is added by `schema.sql` when the API starts (`ADD COLUMN IF NOT EXISTS`, nullable), so an existing database upgrades in place. Rows saved before this change have no domain until they are enriched again, so the cleanup below can only match them by name.

### Cleaning up existing duplicates

`scripts/merge_duplicates.py` finds duplicate rows already in Postgres. Two rows are linked when they share a domain or a name (ignoring case, empty values never match), and rows linked through a chain are one group. In each group it keeps the lowest id whose three answers are not placeholders (or the lowest id if all are), and copies a domain onto the kept row if it had none.

```bash
DB_URL=postgresql://postgres:secret@localhost:5432/gtm uv run python -m scripts.merge_duplicates
```

That prints a dry run and changes nothing, for example:

```text
Group 1 (matched by name 'notion'): keep id 3 https://notion.com, merge id 7 https://notion.so
DRY RUN. Nothing was changed. Re-run with --apply to merge 1 rows.
```

Add `--apply` to change anything. It deletes the duplicate rows and keeps one per group, in a single transaction that rolls back on any error. Back up the database first. Without `DB_URL` it stops with an error. It is not locked against a worker inserting at the same moment, so run it when the worker is idle.

## How the Gemini to Groq fallback works

For each job the worker tries providers in this order, and stops at the first answer:

1. `gemini-3.5-flash`
2. `gemini-3.1-flash-lite`
3. `gemini-3.8-flash`
4. Groq `openai/gpt-oss-20b`

**Cooldowns.** If a Gemini model returns a server error (5xx) or times out (30 seconds), it is put on cooldown: the worker sets a Redis key `cooldown:<model>` that expires after 120 seconds (`COOLDOWN_SECONDS` in `enrich.py`). While that key exists the model is skipped, and the next model is tried straight away. The cooldown lives in Redis, so it applies to every job, not just the one that hit the error. After 120 seconds the model is tried again.

**Groq.** If every Gemini model fails or is cooling down, the worker asks Groq. Groq has no cooldown of its own. If Groq returns a server error, a rate limit error or a connection error, there is nothing left to try and the job fails with `All models are currently busy, please retry in a minute.`

The model that actually answered is saved in the `model` column.

## Limits

- **Static HTML only.** The scraper uses httpx and BeautifulSoup, with no JavaScript rendering. Sites that render on the client, or that block bots, give `Site returned 403` or `No description could be found`.
- **Small input.** The model only sees the page title, the meta description, up to 2000 characters of paragraph text from the first link containing "about" and up to 2000 characters from a customers page when one is linked. It does not crawl further, so thin sites give thin answers.
- **Only some errors trigger fallback.** Gemini 5xx and timeouts cool down and fall through. Other errors, such as a bad API key or a 429 quota error, are not caught there. The job fails with that error text and no fallback runs. The same goes for a bad Groq key.
- **One row per company, never refreshed.** There is no re-enrich endpoint. The API only short circuits on an exact normalised URL, so `notion.so` is queued as a job and the worker then dedupes it by final domain or name (see Duplicates). Paths count for that early check, but a path on an already saved domain is caught by the domain match.
- **Failures are not stored in Postgres.** A failed job only lives in Redis, so the `error` column in `companies` stays empty in practice.
- **Job status expires after 24 hours.** If the worker restarts mid job, that job is marked `failed` and you need to resubmit.
- **One worker, one job at a time.** Throughput is whatever your model quotas and the target site allow.
- **No auth or rate limiting on the API, and Postgres is published on port 5432 with the password `secret`.** This is for local use. Change both before exposing it anywhere.

## Development

Needs [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync
uv run pytest
uv run ruff check .
```

The tests need no network and no API keys. The scraper, the LLM calls and the database connection are all faked.
