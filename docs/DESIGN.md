# Design notes

Depth that used to live in the README: the API reference, the cluster table, the grounding guard, the careers page, answer quality and duplicates, the model fallback, the database migration and the status history. The short version is in [README.md](../README.md).

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

If the URL turns out to be a duplicate of a company that is already saved, the job is still `done`, nothing new is saved, and the job carries two extra fields:

```json
{"status": "done", "url": "https://notion.so", "company_id": 4, "duplicate_of": 4, "matched_by": "domain"}
```

`duplicate_of` is the id of the existing row (the same as `company_id`). `matched_by` is `domain` or `name`, see "Duplicates" below.

An unknown or expired job id returns `404`.

A job still finishes as `done` when the guard rejects the pitch note. A scrape failure, every model being busy, or a placeholder answer (see "Answer quality and duplicates") makes a job `failed`.

### GET /companies/{company_id} and GET /companies

Fetch the result using the `company_id` from a finished job. `GET /companies` lists everything, newest first. The values below are illustrative, the real text comes from the model:

```json
{
  "id": 1,
  "url": "https://example-ap.test",
  "name": "Example AP",
  "domain": "example-ap.test",
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

The pitch fields are:

| field | meaning |
|---|---|
| `cluster` | letter A to G chosen by the model, see the cluster table below |
| `cluster_reason` | one sentence that quotes the site, so you can see why that cluster was picked |
| `demo` | the demo for that cluster, set by code from the cluster, never by the model |
| `customer_pain` | the deployment pain the company's customers have, grounded in the site text |
| `tailoring` | exactly three changes to make to the demo for this company |
| `pitch_note` | the drafted note, or `null` if the guard rejected it twice |
| `pitch_error` | why `pitch_note` is `null`, otherwise `null` |
| `careers_url` | the careers page that was found, or `null` |
| `hiring_fde` | `true`, `false` or `null`, see the careers page section below |
| `domain` | final host after redirects, used to spot duplicates, see Answer quality and duplicates below |

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
| G | computer use and desktop agents | none built (no demo built yet) |

For clusters C to G the `demo` field says `none built`. The note still keeps the two placeholders and pitches the approach. The prompt tells the model to choose G only when the core of the product is an agent that controls a screen, browser or desktop app by clicking and typing.

## How the grounding guard works

The pitch note may only name products and companies that appear in the text the model was given. The check is plain code in `pitch.py`, not another model call. It looks at names only, not at facts (see [Limits](#limits)).

1. **Which words are checked.** Only words that look like a product or company name:
   - a word with an inner capital letter or a digit anywhere in the note, such as `InvoiceGPT`, `G2` or `40`;
   - a capitalised word in the middle of a sentence, such as `Peakflo`;
   - a capitalised word that opens a sentence, only when the next word is `AI`, `Labs` or `Inc` (for example `Acme Labs` or `Together AI`).

   Ordinary sentence openers such as `Simulated` or `Engineers` are not checked. Abbreviations like `e.g.`, `i.e.`, `vs.`, `etc.`, `Dr.` and `Inc.` do not start a new sentence, and numbered list markers such as `1.` are ignored. A trailing `'s` is stripped and the two link placeholders are ignored.
2. **When a checked word passes.** It passes if it appears as a whole word, in any letter case, in the site text the guard knows: the page title, the meta description, the about page text, the customers page text (when the site has one), the matched careers role phrases, the company name and the URL host. A checked word also passes if it is on a short allowed list of words that are never part of a product name: connectives, pronouns, months, days and the author's own vocabulary such as `FDE`, `QA`, `GST`, `Loom` and `India`. `Tally`, `Zoho` and `Hinglish` are not on the list, so a note may name them only when the target's own site does.
3. **Style checks.** At most 150 words, no hyphen or dash characters, and the last line must contain `[LOOM_URL]` and end with `[REPO_URL]`.

If either check fails, the worker asks the model once more. The retry prompt is the original prompt plus the reason, for example `Your previous pitch_note was rejected for: names not found on the site: InvoiceGPT. Write every field again and fix this.`

If the retry fails too, or returns nothing, the job does not fail. The structured fields (cluster, demo, customer pain, tailoring) are kept, `pitch_note` is stored as `null`, `pitch_error` says why, and the job is still `done`. The pitch endpoint then returns the second 404 case above (the one with the stored `pitch_error`).

## Careers page

The scraper also looks for a careers link on the home page (a link whose address or text contains `career`, `jobs`, `join us` or `work with us`) and reads that page. It looks for these role phrases in the page text: forward deployed, solutions engineer, solutions architect, deployment engineer, customer engineer and implementation engineer (singular forms too). Hyphens in the page text are treated as spaces, so `Forward-Deployed` matches.

`hiring_fde` has three values:

- `true`: at least one of those phrases was found. The model gets one line naming them.
- `false`: the page was read and none of the phrases were on it.
- `null`: unknown. There was no careers link, the fetch failed, or the page had no readable text. Many careers pages are hosted by a hiring platform and rendered with JavaScript, so a plain HTTP fetch sees an empty page. Storing `false` there would be wrong.

The model sees only the one hiring line, not the raw careers page text.

## Answer quality and duplicates

### Placeholder answers fail the job

If the model answers `Not available`, `N/A`, `Unknown`, `None` or similar for `industry`, `what_they_sell` or `target_customer`, the job is marked `failed` and nothing is saved. The error names each field and what the model said, for example:

```json
{"status": "failed", "url": "https://example.com", "error": "The model could not fill in target_customer (answered 'Not available') from the site text. The site gave too little to go on, please check the site manually."}
```

Real answers that only contain such a word, such as `None of the above insurance`, are kept. The prompt also tells the model never to describe the customer as a device, an operating system or a generic user group.

### Customers page

When the home page links to a customers page (`/customers`, `/case-studies`, `/use-cases` and close variants, or a link with that visible text), the scraper reads it too: its headings, longer paragraphs and the alt text of customer logos, up to 2000 characters. The model is told to base `target_customer` on it, so the answer names a buyer such as "product and engineering teams at larger companies" instead of "users". Login, help and jobs links are ignored, and only links on the same site are followed. The same text counts as grounded for the guard, so a note may name a customer listed there. If that page cannot be fetched the job carries on without it.

### Duplicates

The same company used to be saved twice, for example `notion.com` and `notion.so` (which redirects to `notion.com`). Now, after the model has answered and before anything is saved, the worker looks for an existing row that matches either way:

- **Final domain.** The host the site ends up on after redirects, lowercased, with `www.` removed. It is stored in the `domain` column.
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
5. Groq `openai/gpt-oss-120b`

**Gemini cooldowns.** A cooldown is a Redis key `cooldown:<model>` with an expiry. While the key exists the model is skipped and the next one is tried straight away. The cooldown lives in Redis, so it applies to every job, not just the one that hit the error. What each Gemini error does:

| error | what happens |
|---|---|
| server error (5xx) or a timeout (30 seconds) | cooldown of 120 seconds, then the next model. A server error also logs its status code and message (cut to 200 characters), so repeated 5xx can be diagnosed |
| 429 (rate limit or quota) | cooldown of 120 seconds, then the next model |
| 404 (model not found) | cooldown of 3600 seconds, then the next model |
| any other 4xx (bad request, bad key, no permission) | logged, no cooldown, then the next model |
| any other exception | not caught, the job fails with the error text |

Because a bad key gets no cooldown, every job still pays a failed call to each Gemini model before it reaches Groq.

**Groq.** If every Gemini model fails or is cooling down, the worker asks Groq. Groq has no cooldown. It tries `openai/gpt-oss-20b` first and `openai/gpt-oss-120b` second. Each request keeps the strict JSON schema and sets `reasoning_effort` to `low` and `max_completion_tokens` to 4096, because these are reasoning models and with the default budget they can spend everything on reasoning and return no JSON. If a model returns a 400 (bad request), a 404, a server error, a rate limit error, a connection error, or JSON that does not fit the schema, the worker logs a line with the status and message only (cut to 200 characters, never headers or keys) and tries the next model. If both fail, the job fails with `All models are currently busy, please retry in a minute.` Any other Groq error, such as a bad key, is not caught and the job fails with that error text, so a bad key stays loud.

The model that actually answered is saved in the `model` column. The pitch retry goes through the same provider order, so a different model can answer it.

## Database migration

`schema.sql` keeps the original `CREATE TABLE IF NOT EXISTS companies` block unchanged and adds one `ALTER TABLE companies ADD COLUMN IF NOT EXISTS ...` line for each of the ten new columns (the nine pitch columns and `domain`), then two `CREATE INDEX IF NOT EXISTS` lines on `lower(domain)` and `lower(name)`. All of the new columns are nullable with no default. The API runs the whole file on every start, so it is safe on an existing table: old rows keep their data and get `NULL` in the new columns, and running it twice changes nothing.

To prove that against a Postgres you have:

```bash
DB_URL=postgresql://user:pass@localhost:5432/dbname uv run python -m scripts.check_migration
```

The script works only inside a throwaway schema called `migration_check`, so it never touches a real `companies` table. It creates the old table, inserts a row, applies `schema.sql` twice, checks the row survived with `NULL` in the new columns, checks the two indexes exist, and prints `MIGRATION OK` as its last line.

## Running it

You need Docker, a Gemini API key and a Groq API key (both have free tiers). This makes real API calls and uses a little of your quota.

```bash
git clone https://github.com/arch-vvc/gtm_agent
cd gtm_agent
cp .env.example .env
```

Put your two keys in `.env`. Leave `DB_URL` and `REDIS_HOST` as they are, they point at the containers.

### Direct run over a list of companies

One URL per line in `targets.txt` (blank lines and `#` comments are ignored):

```bash
printf '# my targets\npeakflo.co\ncekura.ai\n' > targets.txt
docker compose up -d --build
mkdir -p results
docker compose run --rm -v "$PWD/results:/app/results" -v "$PWD/targets.txt:/app/targets.txt" worker /app/.venv/bin/python -m scripts.real_run --file targets.txt --csv results/real_results.csv --resume
```

`results/real_results.csv` holds machine written notes, so it is gitignored and stays on your disk. To read every note as a table, run `uv run python -m scripts.results_table --write`, which writes `private/results_table.md` (also gitignored). `uv run python -m scripts.results_table --check` says whether that file is current, and skips with exit 0 when the CSV is absent. To publish numbers without the notes, run `scripts.export_public` to write `results/eval_results.csv`, which has no note text.

- A line may carry a job post link after the company, for example `ciroos.ai https://jobs.ashbyhq.com/ciroos/<id>`. Greenhouse, Lever and Ashby links are read through their public posting APIs, and the first 3000 characters of the job text are added to what the model sees and to what the grounding guard counts as on the site. Any other link, or a posting that is no longer listed, is ignored and the run carries on with the company site alone.
- `--resume` skips URLs that already have a row without an error in the CSV and retries the rest, so a stopped run carries on where it left off.
- `--delay SECONDS` (default 5) waits between companies to stay inside the free tiers. A `12 of 70` line shows progress.
- URLs can also be given as arguments, and `--provider gemini|groq|all` tests one provider at a time.
- The CSV has one row per URL, errors included. A cell that starts with `=`, `+`, `-` or `@` gets a leading apostrophe, and error text is redacted so keys do not leak.
- Nothing is written to Postgres and nothing is queued. `--help` works without any keys set.
- Without Docker for the app: `uv sync`, start a throwaway Redis (`docker run -d --name gtm-redis -p 6379:6379 redis:7`), load `.env`, then run `REDIS_HOST=localhost uv run python -m scripts.real_run --file targets.txt --csv results/real_results.csv --resume`. Remove it with `docker rm -f gtm-redis`.

### Checking the cluster answers

`evals/golden.csv` holds 38 companies with the cluster label from the author's tracker, set before the engine existed. After a run over those companies, score the CSV (no model call, no keys):

```bash
uv run python -m scripts.golden_eval --csv results/eval_results.csv
```

It prints demo choice (A, B or none, the choice that decides what gets sent), cluster accuracy against the 90 percent target, a confusion matrix, the held out rows on their own, the wrong clusters with the engine's reason, the failures and the companies not run. It exits 1 when demo choice is below the floor in `evals/floor.json` (add `--floor-file evals/floor.json`). The labels are one person's judgement and the clusters overlap, so this measures agreement with the tracker, not truth. Results and known limits are in [EVAL.md](EVAL.md).

### The service in 5 minutes

```bash
docker compose up -d --build
curl -X POST localhost:8000/enrich -H 'content-type: application/json' -d '{"url":"stripe.com"}'
curl localhost:8000/jobs/<job_id>
curl localhost:8000/companies/<company_id>/pitch
```

This starts Postgres, Redis, the API on http://localhost:8000 and a background worker. Poll the job until `status` is `done`, then read the company and its pitch. `docker compose logs app worker` shows output and `docker compose down` stops everything (data stays in the `gtm_pgdata` volume). The default database password is for local use only; set `POSTGRES_PASSWORD` in `.env` to change it. The endpoint reference is the API section above.

## Limits

- **Partial live evidence.** The tests mock the models. One live run covered 31 of 38 golden companies (27 answered, 4 failed) and was stopped by hand, so seven companies were never tried. The saved run is older than the code. See [EVAL.md](EVAL.md) for the numbers and what they do and do not show.
- **The guard checks names, not facts.** A number written as digits must appear on the site, but an invented claim made of ordinary words, such as "cuts errors by half", passes. An invented name written in lower case passes too, and so does an invented name made only of words that each appear somewhere on the site.
- **The demo claim check is phrase matching.** It missed 4 of 5 paraphrased latency claims, so treat it as a known limit and not coverage.
- **A name that opens a sentence is not caught by design**, unless the next word is `AI`, `Labs` or `Inc`.
- **The guard checks `pitch_note` only.** `customer_pain`, `tailoring` and `cluster_reason` can still contain names the site never mentioned.
- **Style is partly enforced by the prompt only.** The word limit, the dash ban and the placeholder line are checked by code. British English and the conclusion first structure are only asked for in the prompt.
- **Scraped page text is untrusted.** It is fenced in the prompt and the model is told not to follow instructions inside it. That reduces prompt injection but does not eliminate it, and a name an attacker puts in the page counts as grounded.
- **The model can pick the wrong cluster.** The mapping from cluster to demo is code, but the cluster letter is the model's judgement. Read `cluster_reason`.
- **Static HTML only.** No JavaScript rendering, so client rendered or bot blocking sites give `Site returned 403`, thin input or `hiring_fde` of `null`.
- **The scraper checks every address it fetches.** Private, local and non standard port addresses are refused, but the host is resolved once for the check and again when connecting, so DNS rebinding is not fully closed.
- **Small input.** The model sees the page title, the meta description, up to 2000 characters from the about page, up to 2000 from a customers page and one hiring line.
- **Name matching can merge companies** that share a main domain label on different TLDs.
- **Old rows have no pitch, and there is no re-enrich endpoint.**
- **Failures are not stored in Postgres.** A failed job only lives in Redis, and job status expires after 24 hours.
- **One worker, one job at a time.**
- **No approval step in the database.** Notes are drafts. A Postgres approval status column and an approve endpoint are the next step, not built.
- **For local use only.** There is no auth or rate limiting on the API. Docker publishes the API and Postgres on 127.0.0.1 only, with the default password `secret`. Change both before exposing it anywhere.

## Status history

These are the detailed notes the README Status section summarises.

- **Verified:** the test suite (576 tests, all model calls mocked), the migration check against Postgres 16, and an end to end run against real Postgres and Redis with a faked scraper and a faked model.
- **Latest live run (author's machine, real Gemini and Groq):** Peakflo (cluster B) and Cekura (cluster A) were enriched. Simular failed: two Gemini models returned 503 "high demand" (a capacity error on Google's side), a third was cooling down, and the Groq `openai/gpt-oss-20b` model answered `UNKNOWN` for industry. The junk check then failed the job without trying the second Groq model, `openai/gpt-oss-120b`.
- **Problem seen in that run, fixed and NOT yet re-run live:** Cekura's note claimed past work ("I adapted the simulation engine") that the demo fact sheet does not support. The guard checks names and figures, not claims. Two fixes are covered by mocked tests: a junk answer now counts as a failed attempt and falls through to the next model, and a deterministic check rejects first person past tense work claims other than "I built" and rejects "I built" for clusters with no demo built, so the retry prompt names the problem.
- **Earlier problems, fixed and NOT yet re-run live:** two first drafts were rejected by the guard because it did not accept figures from the author's own demo fact sheet, and one note invented a deadline. Both are covered by mocked tests.
- **Groq:** an earlier live Groq failure (`json_validate_failed`) was fixed with low reasoning effort and a 4096 token budget, and a Groq answer was seen live for Peakflo after that fix. The second Groq model and the Gemini server error logging have not been exercised live.
- **Results:** the committed `results/real_results.csv` comes from an earlier run on older code, and the Results placeholder below is updated separately, so it stays.
- **Earlier live runs** on the author's machine exposed three problems: a company saved with every field `Not available`, a customer described as a device user group, and the same company saved twice under two domains. They are addressed in code and covered by mocked tests (junk answers are rejected, the prompt asks for the buyer type and reads the customers page, duplicates are merged on final domain), but not re-run live.
