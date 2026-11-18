# gtm_agent

gtm_agent is a pitch engine for forward deployed engineer (FDE) outreach. You give it a startup's URL. It returns the cluster the company belongs to (A to G), the demo to send, the deployment pain the company's customers likely have, three changes to tailor the demo, and a pitch note of 150 words or fewer that names only things found on the company's own site (a name check, not a fact check, see [Limits](#limits) for the honest caveat). It also reports whether the company's careers page lists a forward deployed or solutions engineer role.

## Results

<!-- results:start -->
| Company | Cluster | Demo | Hiring FDE | Cluster reason (quoted from the site) | Note (first line) | What the automatic checks found |
|---|---|---|---|---|---|---|
| Peakflo | B | invoice-exception-triage | yes | Peakflo helps finance teams eliminate manual work across the entire invoice to cash and procure to pay operations. | I built a demo that automates three way matching to understand how finance teams at companies like Ninja Van can reduce manual effort. I would adapt the demo to handle the specific document types used in their invoice to... | none found by the automatic checks |
| Cozmo | n/a | n/a | unknown |  |  | failed: Could not reach site |
| Telnyx | A | voice-agent-call-qa | yes | Telnyx is the only licensed carrier that owns its AI infrastructure end to end and powers platforms like Talkdesk and Kindred Voice. | I built a voice agent evaluation tool to help Telnyx customers stress test their AI agents against adversarial scenarios before deploying them on your private network. First, I would adapt the simulation environment to t... | none found by the automatic checks |
| Prodigal | n/a | n/a | unknown |  |  | failed: The model could not fill in industry \(answered 'UNKNOWN'\), what_they_sell \(answered 'UNKNOWN'\), target_customer \(answered 'UNKNOWN'\) from the site text. The site gave too little to go on, please check the site manually. |
| Turing | C | none built | no | Turing works with Fortune 500 enterprises to build and deploy end to end agentic AI systems inside mission critical workflows. | I would build a demonstration for your enterprise agentic AI systems that bridges the gap between research models and mission critical deployment for Fortune 500 clients. | none found by the automatic checks |
| Ciroos | E | none built | yes | Ciroos provides AI SRE tools designed for distributed systems and modern and legacy applications. | I would build a validation tool that cross references system logs against known incident patterns to ensure reliability in complex production environments. First, I would adapt the framework to map logs across multi clou... | none found by the automatic checks |
| Neuralconcept | F | none built | yes | Neural Concept is an AI platform redefining how leading teams design complex products. | I would build a validation framework that mirrors your design optimization platform to help your engineers automate the review of simulation outcomes against product constraints. | none found by the automatic checks |
| Certa | F | none built | no | Certa is a no code operating system that serves as a collection of tools to map relationships and carry trust across the entire third party lifecycle. | I would build a validation tool for vendor onboarding data that automates compliance checks for companies like Quantcast to accelerate their lifecycle management. First, I would adapt the interface to process vendor onbo... | none found by the automatic checks |
| Blitzy | E | none built | no | Blitzy describes itself as an autonomous AI platform that provides an execution layer of the SDLC to accelerate the full development lifecycle. | I would build a migration validator that tests autonomous code generation outputs against legacy enterprise codebase standards to ensure production readiness without manual review. First, this tool will verify if generat... | none found by the automatic checks |
| Hackerrank | F | none built | no | HackerRank is the market leading coding test and interview solution for hiring developers. | I would build a validation tool that cross references candidate assessment results with hiring manager interview feedback to identify discrepancies in the hiring funnel, which helps companies like Prudential ensure they... | none found by the automatic checks |
| Arcesium | B | invoice-exception-triage | no | "cloud native solutions help clients in the investment industry transform operations with new and better financial data management." |  | note rejected: Pitch note rejected and the retry was rejected too: note contains a hyphen or dash character \(U+2011\); names not found on the site: NAV |
| Fibr | F | none built | unknown | We are building the Agentic Web, where every URL is an autonomous, context aware agent that detects visitor signals, decodes intent, and rewrites the experience... |  | note rejected: Pitch note rejected and the retry answered with placeholder fields: names not found on the site: Chief, Officer |
| Revrag | A | voice-agent-call-qa | yes | “Embed AI agents directly into your BFSI product. Automate onboarding, re engage drop offs, and drive conversions with In App and Calling AI agents.” | I built the voice agent call QA demo to show how I would work on your customers’ deployment problems, adapted using the tailoring changes. | none found by the automatic checks |
| Shortloop | A | voice-agent-call-qa | no | "AI phone agents for service, sales, and outbound teams that want a polished customer experience around the clock." |  | note rejected: Pitch note rejected and the retry was rejected too: note contains a hyphen or dash character \(U+2011\); names not found on the site: 17, 5 |
| Joinhandshake | F | none built | no | Handshake is a three sided job marketplace that connects knowledge workers, educational institutions, and employers through a career network. | I would build a dashboard that visualises the matching of talent to opportunity across your three sided marketplace to help resolve the inefficiencies of a broken and selective recruiting system. | none found by the automatic checks |
| Bluemachines | n/a | n/a | unknown |  |  | failed: The model could not fill in industry \(answered 'UNKNOWN'\), target_customer \(answered 'UNKNOWN'\) from the site text. The site gave too little to go on, please check the site manually. |
| Emergent | F | none built | no | Emergent is a no code platform that allows users to transform ideas into production ready web and mobile apps. | I would build a project deployment workflow for Emergent that allows non technical users to map business requirements to functional app modules and I will show how this accelerates time to value for customers like medica... | none found by the automatic checks |
| Devrev | A | voice-agent-call-qa | no | The company describes its product as a platform that uses a knowledge graph to power enterprise search, employee service desks, and self service customer suppor... | I built a voice agent evaluation tool to identify failing turns in customer support interactions, which aligns with the goal of helping teams resolve tickets faster as seen at companies like S&amp;P Global. First, I would ad... | none found by the automatic checks |
| Cartesia | A | voice-agent-call-qa | no | Cartesia builds real time voice AI and production voice agents for enterprises. | I built a voice agent call QA tool that stress tests conversational scripts to ensure sub 100ms latency and high reliability for production grade voice agents. | none found by the automatic checks |
| Avaamo | A | voice-agent-call-qa | yes | Avaamo focuses on AI agents that understand, reason and resolve, across healthcare, workplace and customer experience. | I built a voice agent call QA demo to evaluate resolution accuracy which aligns with your goal to automate customer conversations for enterprises like UCHealth. | none found by the automatic checks |
| Wonderful | A | voice-agent-call-qa | yes | We take your most critical workflows into production across the enterprise, in weeks, not months. | I built a voice agent QA demo that showcases how I can evaluate and improve Wonderful’s billing agent for Telefónica Colombia. | none found by the automatic checks |
| Notion | n/a | n/a | yes |  |  | failed: The model could not fill in industry \(answered 'UNKNOWN'\) from the site text. The site gave too little to go on, please check the site manually. |
| Databricks | E | none built | yes | Databricks offers a unified platform for data, analytics and AI. |  | note rejected: Pitch note rejected and the retry was rejected too: note contains a hyphen or dash character \(U+2011\); names not found on the site: ACID, CFO |
| Happyrobot | D | none built | yes | AI workers deployed into the operations that move goods, keep the lights on, and settle transactions |  | note rejected: Pitch note rejected and the retry answered with placeholder fields: names not found on the site: Ops, Manager |
| Furtherai | B | invoice-exception-triage | no | "The AI platform for commercial insurance underwriting, claims and policy operations." | I would build a demo that showcases how FurtherAI can cut quote turnaround from minutes to seconds, demonstrating the 30x speedup experienced by Leavitt Group. First, I would model the quote workflow to reflect the carri... | none found by the automatic checks |
| Salespatriot | D | none built | yes | We build the AI operating system for complex procurement and distribution across defense, aerospace, and industrial sectors. | I would build a procurement workflow automation tool that integrates fragmented DIBBS data to help defense contractors like Echelon Supply &amp; Service move from reactive chaos to continuous execution. | none found by the automatic checks |
| Palantir | C | none built | unknown | They empower organizations to effectively integrate their data, decisions, and operations. | I would build a system that maps operational data inputs to automated decision logic to address the fragmentation of data and operations within large organizations. First, I would adapt the data integration flows to map... | none found by the automatic checks |
| Cekura | A | voice-agent-call-qa | yes | Cekura provides an end to end voice testing and voice observability platform for automated QA of voice AI and chat AI agents. | I built demo A to understand how voice AI platforms ensure instruction following and tool call reliability for teams like Nurix and Kastle. I would adapt this by replacing general scripts with healthcare compliance scena... | none found by the automatic checks |
| Collectwise | A | voice-agent-call-qa | unknown | CollectWise is the leading AI agent platform for the debt collection industry, automating phone calls and critical workflows. | I built a voice agent call QA tool to demonstrate how I would help your team validate the performance of your AI agents against complex debt recovery scripts. First, I would adapt the simulation parameters to mimic the s... | none found by the automatic checks |
| Regal | A | voice-agent-call-qa | yes | The company describes its product as "The AI agent platform for enterprise contact centers. Build, test, and scale voice AI agents, proven across 500M+ calls." | I built a voice agent call QA tool to understand the testing hurdles contact centers face when deploying automated agents for workflows like first notice of loss. | none found by the automatic checks |
| Livekit | E | none built | yes | LiveKit provides "an open source framework and developer platform for building, testing, deploying, scaling, and observing agents in production." | I would build a migration validator to help teams at customers like OpenAI and Nvidia safely transition real time media infrastructure to LiveKit as their default infrastructure layer for building AI. | none found by the automatic checks |
| Loadsmart | F | none built | no | Loadsmart AI is a vertical SaaS platform that runs freight and warehouse work end to end using AI agents. | I would build a validation tool for your eleven AI agents that monitors for tender failures and dock schedule management errors to ensure consistency in your freight lifecycle data. | none found by the automatic checks |

_Generated by scripts/results_table.py from results/real_results.csv. The automatic checks look at names, figures, dashes, the note length and made up claims of past work. They do not prove a note is true, read every note before sending it._
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

- A line may carry a job post link after the company, for example `ciroos.ai https://jobs.ashbyhq.com/ciroos/<id>`. Greenhouse, Lever and Ashby links are read through their public posting APIs, and the first 3000 characters of the job text are added to what the model sees and to what the grounding guard counts as on the site. Any other link, or a posting that is no longer listed, is ignored and the run carries on with the company site alone.
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

- **Partial live evidence.** The tests mock the models. One live run covered 32 of 39 targets (28 answered, 4 failed) and was stopped by hand, so seven companies were never tried. Free tier cooldowns and 504 errors made it slow. The cluster is the model's judgement and has not been checked against a labelled set yet.
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
- **Seen live:** a 32 company run with real Gemini and Groq from the current code (see Results). 28 were enriched. 4 failed (one site unreachable, three with `UNKNOWN` answers). 5 enriched rows have no note because the guard rejected it twice, three of them for a non breaking hyphen (U+2011) the model kept writing.
- **Not yet checked live:** the scraper address checks are covered by mocked tests only.
- **Results:** the table above comes from `results/real_results.csv` (32 rows, one run, not cherry picked).
- Full history: [docs/DESIGN.md](docs/DESIGN.md#status-history).

## Development

Needs [uv](https://docs.astral.sh/uv/) and Python 3.13. The tests need no network and no API keys.

```bash
uv sync
uv run pytest
uv run ruff check .
```
