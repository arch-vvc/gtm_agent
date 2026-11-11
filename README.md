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

An unknown or expired job id returns `404`.

### GET /companies/{company_id} and GET /companies

Fetch the result using the `company_id` from a finished job. `GET /companies` lists everything, newest first. The values below are illustrative, the real text comes from the model:

```json
{
  "id": 1,
  "url": "https://stripe.com",
  "name": "Stripe",
  "industry": "Financial technology",
  "what_they_sell": "Payment processing APIs and billing software",
  "target_customer": "Online businesses and platforms of any size",
  "model": "gemini-3.5-flash",
  "error": null,
  "created_at": "2026-11-11T06:46:21.337804+00:00"
}
```

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
- **Small input.** The model only sees the page title, the meta description and up to 2000 characters of paragraph text from the first link containing "about". It does not crawl further, so thin sites give thin answers.
- **Only some errors trigger fallback.** Gemini 5xx and timeouts cool down and fall through. Other errors, such as a bad API key or a 429 quota error, are not caught there. The job fails with that error text and no fallback runs. The same goes for a bad Groq key.
- **One row per URL, never refreshed.** There is no re-enrich endpoint. Paths count, so `stripe.com/about` is a different row from `stripe.com`.
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
