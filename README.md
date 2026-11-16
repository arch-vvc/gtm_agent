# gtm_agent

gtm_agent is a pitch engine for forward deployed engineer (FDE) outreach. You give it a startup's URL. It returns the cluster the company belongs to (A to G), the demo to send, the deployment pain the company's customers likely have, three changes to tailor the demo, and a pitch note of 150 words or fewer that names only things found on the company's own site (a name check, not a fact check, see [Limits](#limits) for the honest caveat). It also reports whether the company's careers page lists a forward deployed or solutions engineer role.

## Results

<!-- results:start -->
> PLACEHOLDER (replace before sending to anyone): the real results go here. Run the commands in "Try it" below, commit the output as `results/real_results.csv`, then replace the skeleton table with a few rows from that file. Failures are shown, not hidden: keep rows where a note was rejected or the model answered badly. Nothing in this section is a real result yet.

| company | cluster | demo | hiring FDE | cluster_reason (quoted from the site) | first line of the note | what went wrong |
|---|---|---|---|---|---|---|
| PLACEHOLDER | | | | | | |
<!-- results:end -->

To refresh the table after a run, commit `results/real_results.csv` and run `uv run python -m scripts.results_table --write-readme`. It replaces only the block between the results markers. `uv run python -m scripts.results_table --check` verifies that the README matches the CSV.

When you read the CSV, look for a wrong cluster (compare `cluster_reason` with what the company really does), rows where `pitch_note` is empty and `pitch_error` says the guard rejected it, and junk answers in `customer_pain` or `tailoring`.

## Try it

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

Then commit `results/real_results.csv` and run `uv run python -m scripts.results_table --write-readme` to fill the Results table.

- `--resume` skips URLs that already have a row without an error in the CSV and retries the rest, so a stopped run carries on where it left off.
- `--delay SECONDS` (default 5) waits between companies to stay inside the free tiers. A `12 of 70` line shows progress.
- URLs can also be given as arguments, and `--provider gemini|groq|all` tests one provider at a time.
- The CSV has one row per URL, errors included. A cell that starts with `=`, `+`, `-` or `@` gets a leading apostrophe, and error text is redacted so keys do not leak.
- Nothing is written to Postgres and nothing is queued. `--help` works without any keys set.
- Without Docker for the app: `uv sync`, start a throwaway Redis (`docker run -d --name gtm-redis -p 6379:6379 redis:7`), load `.env`, then run `REDIS_HOST=localhost uv run python -m scripts.real_run --file targets.txt --csv results/real_results.csv --resume`. Remove it with `docker rm -f gtm-redis`.

### The service in 5 minutes

```bash
docker compose up -d --build
curl -X POST localhost:8000/enrich -H 'content-type: application/json' -d '{"url":"stripe.com"}'
curl localhost:8000/jobs/<job_id>
curl localhost:8000/companies/<company_id>/pitch
```

This starts Postgres, Redis, the API on http://localhost:8000 and a background worker. Poll the job until `status` is `done`, then read the company and its pitch. `docker compose logs app worker` shows output and `docker compose down` stops everything (data stays in the `gtm_pgdata` volume). The default database password is for local use only; set `POSTGRES_PASSWORD` in `.env` to change it. Full endpoint reference: [docs/DESIGN.md](docs/DESIGN.md).

## How it works

1. `POST /enrich` normalises the URL and queues a job in Redis. The scraper refuses private and local addresses.
2. The worker reads the home page, the about page, a customers page and the careers page (static HTML only).
3. A model picks the cluster, the deployment pain, three tailoring changes and a pitch note. Gemini is tried first, Groq is the fallback, and Redis cooldowns skip a model that just failed.
4. Code, not the model, maps the cluster to a demo.
5. A grounding guard in `pitch.py` checks the note against the site text: names only, at most 150 words, no dashes, the two link placeholders present. It retries once.
6. Junk answers fail the job, duplicates are merged on final domain or name, and the row is saved in Postgres.

Cluster table, grounding guard rules, fallback behaviour, duplicates and the database migration are in [docs/DESIGN.md](docs/DESIGN.md).

## Limits

- **Little live evidence.** The tests mock the models. Only a three company live run has been seen, and the fact sheets, the future tense rule, the second Groq model and the server error logging have not been re-run live, so the guard's false positive rate is unproven against the real APIs.
- **The guard checks names, not facts.** A number written as digits must appear on the site, but an invented claim made of ordinary words, such as "cuts errors by half", passes. An invented name written in lower case passes too, and so does an invented name made only of words that each appear somewhere on the site.
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
- **For local use only.** There is no auth or rate limiting on the API. Docker publishes the API and Postgres on 127.0.0.1 only, with the default password `secret`. Change both before exposing it anywhere.

## Status

- **Verified by mocked tests:** 632 tests pass with every model, Redis and Postgres call faked, plus the migration check against Postgres 16 and an end to end run against real Postgres and Redis with a faked scraper and model.
- **Seen live once:** a three company run on the author's machine with real Gemini and Groq. Peakflo and Cekura were enriched, Simular failed on model capacity errors.
- **Fixed but NOT yet re-run live:** the past tense claim check, junk answers falling through to the next model, the fact sheet figures, the second Groq model, the scraper address checks and `--file` with `--resume`.
- **Results:** the table above is a placeholder until a live run from the final code is committed.
- Full history: [docs/DESIGN.md](docs/DESIGN.md#status-history).

## Development

Needs [uv](https://docs.astral.sh/uv/) and Python 3.13. The tests need no network and no API keys.

```bash
uv sync
uv run pytest
uv run ruff check .
```
