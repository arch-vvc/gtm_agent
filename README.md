# gtm_agent

Give it a company website and it returns the company's industry, what they sell and who they sell to. It also picks a cluster for the company, maps that to one of the demos in the pitch repos, names the deployment pain the company's customers have, suggests three changes to tailor the demo, and drafts a pitch note of 150 words or fewer. A guard checks that the note names nothing that is not on the company's own site.

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

Then read the result, and the pitch if there is one:

```bash
curl localhost:8000/companies/<company_id>
curl localhost:8000/companies/<company_id>/pitch
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

If that URL was already enriched, you get the saved row straight away instead of a job. The row has the same fields as `GET /companies/{company_id}` below, plus `"status": "already in the table"`.

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

A job still finishes as `done` when the guard rejects the pitch note. Only a scrape failure or every model being busy makes a job `failed`.

### GET /companies/{company_id} and GET /companies

Fetch the result using the `company_id` from a finished job. `GET /companies` lists everything, newest first. The values below are illustrative, the real text comes from the model:

```json
{
  "id": 1,
  "url": "https://example-ap.test",
  "name": "Example AP",
  "industry": "Accounts payable automation",
  "what_they_sell": "Software that matches invoices, purchase orders and payments for finance teams",
  "target_customer": "Finance teams at growing Indian businesses",
  "model": "gemini-3.5-flash",
  "error": null,
  "created_at": "2026-11-11T06:46:21.337804+00:00",
  "cluster": "B",
  "cluster_reason": "The site says it \"automates accounts payable for finance teams\".",
  "demo": "invoice-exception-triage",
  "customer_pain": "Finance teams match invoices, purchase orders and payments by hand, so errors are found late.",
  "tailoring": [
    "Use Tally style export columns in the sample data",
    "Name the personas after AP clerks and a finance controller",
    "Say GST and purchase order, not VAT and requisition"
  ],
  "pitch_note": "Example AP automates accounts payable for finance teams, so a demo that flags every three way match mismatch fits its customers well.\n\nThe site says it automates accounts payable for finance teams, so wrong amounts and duplicates are a daily risk for them. The demo reads messy invoice, purchase order and payment exports and shows the rupees at risk.\n\nLoom: [LOOM_URL] Repo: [REPO_URL]",
  "pitch_error": null,
  "careers_url": "https://example-ap.test/careers",
  "hiring_fde": false
}
```

The new fields are:

| field | meaning |
|---|---|
| `cluster` | letter A to F chosen by the model, see the cluster table below |
| `cluster_reason` | one sentence that quotes the site, so you can see why that cluster was picked |
| `demo` | the demo for that cluster, set by code from the cluster, never by the model |
| `customer_pain` | the deployment pain the company's customers have, grounded in the site text |
| `tailoring` | exactly three changes to make to the demo for this company |
| `pitch_note` | the drafted note, or `null` if the guard rejected it twice |
| `pitch_error` | why `pitch_note` is `null`, otherwise `null` |
| `careers_url` | the careers page that was found, or `null` |
| `hiring_fde` | `true`, `false` or `null`, see the careers page section below |

Rows enriched before the pitch engine existed have `null` in all of these fields. They still come back fine from both endpoints.

### GET /companies/{company_id}/pitch

Returns the pitch as markdown (`Content-Type: text/markdown`). The values are illustrative:

```markdown
# Pitch for Example AP

Cluster: B
Demo: invoice-exception-triage
Hiring FDE: no

## Note

Example AP automates accounts payable for finance teams, so a demo that flags every three way match mismatch fits its customers well.

The site says it automates accounts payable for finance teams, so wrong amounts and duplicates are a daily risk for them. The demo reads messy invoice, purchase order and payment exports and shows the rupees at risk.

Loom: [LOOM_URL] Repo: [REPO_URL]

## Tailoring

- Use Tally style export columns in the sample data
- Name the personas after AP clerks and a finance controller
- Say GST and purchase order, not VAT and requisition
```

`Hiring FDE` shows `yes`, `no` or `unknown`. The two placeholders `[LOOM_URL]` and `[REPO_URL]` are left in on purpose. Replace them with your own links before you send anything.

There are four 404 cases, and each has its own `detail`:

1. No row with that id: `{"detail": "Company not found"}`
2. The row has a `pitch_error`, because the guard rejected the note twice: `{"detail": "No pitch for this company: <pitch_error>"}`, where `<pitch_error>` is the stored reason.
3. An old row with no note, no `pitch_error` and no cluster, so it was enriched before the pitch engine existed: `{"detail": "No pitch for this company: it was enriched before the pitch engine existed"}`
4. A row with a cluster but no note and no `pitch_error`: `{"detail": "No pitch for this company: no note was saved"}`. This should not happen in normal use, it means the row has pitch fields but the note was never stored.

## Clusters and demos

The model picks one cluster letter. Code turns the letter into a demo, so the model can never invent a demo name.

| cluster | kind of company | demo |
|---|---|---|
| A | voice and conversational agents | `voice-agent-call-qa` |
| B | finance, insurance, back office | `invoice-exception-triage` |
| C | enterprise AI deployment | none built (planned: SOP to agent kit) |
| D | supply chain and physical ops | none built (planned: capstone spin off) |
| E | AI infra and dev tools | none built (planned: migration validator) |
| F | vertical SaaS | none built (no default demo) |

For clusters C to F the `demo` field says `none built`. The note still keeps the two placeholders and pitches the approach.

## How the grounding guard works

The pitch note may only name products, customers and tools that appear in the text the model was given. The check is plain code in `pitch.py`, not another model call.

1. It collects every capitalised word in `pitch_note`, and every word with an inner capital or a digit, such as `Peakflo`, `InvoiceGPT` or `G2`. A trailing `'s` is stripped and the two link placeholders are ignored.
2. A word passes if it appears as a whole word, in any letter case, in the site text (title, description, about page text, the matched careers role phrases, the company name and the URL host). It also passes if it is on a short allowed list: sentence starters, pronouns, months, days and the user's own vocabulary such as `FDE`, `QA`, `GST` and `Loom`.
3. A style check runs too: at most 150 words, no hyphen or dash characters, and the last line must contain `[LOOM_URL]` and end with `[REPO_URL]`.

If either check fails, the worker asks the model once more. The retry prompt is the original prompt plus the reason, for example `Your previous pitch_note was rejected for: names not found on the site: InvoiceGPT. Write every field again and fix this.`

If the retry fails too, or returns nothing, the job does not fail. The structured fields (cluster, demo, customer pain, tailoring) are kept, `pitch_note` is stored as `null`, `pitch_error` says why, and the job is still `done`. The pitch endpoint then returns the second 404 case above (the one with the stored `pitch_error`).

## Careers page

The scraper also looks for a careers link on the home page (a link whose address or text contains `career`, `jobs`, `join us` or `work with us`) and reads that page. It looks for these role phrases in the page text: forward deployed, solutions engineer, solutions architect, deployment engineer, customer engineer and implementation engineer (singular forms too). Hyphens in the page text are treated as spaces, so `Forward-Deployed` matches.

`hiring_fde` has three values:

- `true`: at least one of those phrases was found. The model gets one line naming them.
- `false`: the page was read and none of the phrases were on it.
- `null`: unknown. There was no careers link, the fetch failed, or the page had no readable text. Many careers pages are hosted by a hiring platform and rendered with JavaScript, so a plain HTTP fetch sees an empty page. Storing `false` there would be wrong.

The model sees only the one hiring line, not the raw careers page text.

## How the Gemini to Groq fallback works

For each job the worker tries providers in this order, and stops at the first answer:

1. `gemini-3.5-flash`
2. `gemini-3.1-flash-lite`
3. `gemini-3.8-flash`
4. Groq `openai/gpt-oss-20b`

**Cooldowns.** If a Gemini model returns a server error (5xx) or times out (30 seconds), it is put on cooldown: the worker sets a Redis key `cooldown:<model>` that expires after 120 seconds (`COOLDOWN_SECONDS` in `enrich.py`). While that key exists the model is skipped, and the next model is tried straight away. The cooldown lives in Redis, so it applies to every job, not just the one that hit the error. After 120 seconds the model is tried again.

**Groq.** If every Gemini model fails or is cooling down, the worker asks Groq. Groq has no cooldown of its own. If Groq returns a server error, a rate limit error or a connection error, there is nothing left to try and the job fails with `All models are currently busy, please retry in a minute.` The same happens if Groq answers with JSON that does not fit the schema.

The model that actually answered is saved in the `model` column. The pitch retry goes through the same provider order, so a different model can answer it.

## Database migration

`schema.sql` keeps the original `CREATE TABLE IF NOT EXISTS companies` block unchanged and adds one `ALTER TABLE companies ADD COLUMN IF NOT EXISTS ...` line for each of the nine new columns. All of them are nullable with no default. The API runs the whole file on every start, so it is safe on an existing table: old rows keep their data and get `NULL` in the new columns, and running it twice changes nothing.

To prove that against a Postgres you have:

```bash
DB_URL=postgresql://user:pass@localhost:5432/dbname uv run python -m scripts.check_migration
```

The script works only inside a throwaway schema called `migration_check`, so it never touches a real `companies` table. It creates the old table, inserts a row, applies `schema.sql` twice, checks the row survived with `NULL` in the new columns, and prints `MIGRATION OK` as its last line.

## Real run

The tests mock the models. To see what the real models do on real sites, run the pitch engine directly. This calls `enrich.enrich(url)` for each URL, writes nothing to Postgres and queues nothing:

```bash
docker compose up -d --build
docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run peakflo.co cekura.ai
```

Run it inside the worker container, because it has your keys and a Redis for the Gemini cooldowns. To test one provider at a time:

```bash
docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run --provider gemini cekura.ai
docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run --provider groq peakflo.co
```

For each URL it prints the full result as JSON (company fields, demo, model, pitch note, pitch error, careers URL, `hiring_fde`, error), which provider and model answered, and the pitch markdown. It prints a `WARNING` line when `pitch_note` is `null`, with the `pitch_error`. If a call raises, for example a bad API key or a 429, it prints an `ERROR: <exception class>: <message>` line and carries on with the next URL. The exit code is non zero if any URL ended with an error. `--help` works without any keys set.

## Limits

- **Tested with mocked models only.** The pitch engine has not been run against the real Gemini or Groq APIs, so no live output exists yet. Until someone runs the real run above with their own keys, treat the Groq strict schema, the Gemini schema handling and the guard's false positive rate as unproven.
- **The guard checks names, not facts.** An invented figure such as "cut errors by 40%" passes. An invented name written in lower case passes too, and so does an invented name made only of words that each appear somewhere on the site.
- **The guard checks `pitch_note` only.** `customer_pain`, `tailoring` and `cluster_reason` can still contain names the site never mentioned.
- **Style is partly enforced by the prompt only.** The word limit, the dash ban and the placeholder line are checked by code. British English and the conclusion first structure are only asked for in the prompt, and nothing verifies them.
- **Scraped page text is untrusted.** It is fenced in the prompt with a tag and the model is told not to follow instructions inside it. That reduces prompt injection but does not remove it. A name an attacker puts in the page text counts as grounded, because the guard trusts the site text.
- **The model can pick the wrong cluster.** The mapping from cluster to demo is code, but the cluster letter is the model's judgement. Read `cluster_reason` to see what it relied on.
- **Old rows have no pitch.** Companies enriched before this change have `null` pitch fields and the pitch endpoint returns 404 for them. There is no re-enrich endpoint yet.
- **`hiring_fde` is often `null`.** Careers pages rendered with JavaScript or hosted on a hiring platform cannot be read by this scraper.
- **Static HTML only.** The scraper uses httpx and BeautifulSoup, with no JavaScript rendering. Sites that render on the client, or that block bots, give `Site returned 403` or `No description could be found`.
- **Small input.** The model only sees the page title, the meta description, up to 2000 characters of paragraph text from the first link containing "about", and one hiring line from the careers page. It does not crawl further, so thin sites give thin answers.
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
