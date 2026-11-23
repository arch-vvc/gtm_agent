# gtm_agent

gtm_agent is a pitch engine for forward deployed engineer (FDE) outreach. You give it a startup's URL. It returns the cluster the company belongs to (A to G), the demo to send, the deployment pain the company's customers likely have, three changes to tailor the demo, and a pitch note of 150 words or fewer that names only things found on the company's own site. It also reports whether the careers page lists a forward deployed or solutions engineer role.

I measured it against 38 companies I had labelled by hand before the engine existed. It is good enough to pick the right demo most of the time, and not good enough to pick the right cluster. Both numbers are below.

## Results

Scored by `scripts.golden_eval` from the saved live run `results/eval_results.csv`, which was made at commit `fcd391e` (the code has changed since, see Limits):

```
demo choice (A, B or none): 23 of 27 answered (85%)
cluster accuracy: 16 of 27 answered (59%)   BELOW the 90% target
```

Demo choice is the headline, because it decides what gets sent. Cluster accuracy is the stricter test and it misses its 90% target by 31 points. Rows are my label, columns are what the engine picked:

```
          A    B none
A         7    0    1
B         1    3    1
none      1    0   13
```

27 of 38 companies were answered. 4 failed before a cluster and 7 were never run. The full 7 by 7 matrix, the failure buckets and the known limits of this eval are in [docs/EVAL.md](docs/EVAL.md).

## What I tried, where it stopped, what is next

- **Tried.** A model reads the home, about, customers and careers pages and picks a cluster. Code maps the cluster to a demo. A guard in `pitch.py` checks the note against the site text. I ran it live over the golden set and scored it by script.
- **Stopped.** Cluster accuracy is 59% against a 90% target. 7 of the 11 wrong clusters are harmless (both sides mean no demo). 4 change what gets sent: Certa, DevRev, CollectWise and LiveKit.
- **Fixed since.** The guard rejected 5 notes for a non breaking hyphen, acronyms and job titles. That is fixed in code, and a new check rejects claims about the demo that its fact sheet does not support.
- **Next.** Re run the 7 never run companies live, because only they are a clean test. Read the 4 harmful misses by hand. Get a second labeller.

## Run it

You need [uv](https://docs.astral.sh/uv/) and Python 3.13. Scoring and the tests need no network and no keys:

```bash
uv sync
uv run python -m scripts.golden_eval --csv results/eval_results.csv --floor-file evals/floor.json
```

That prints the numbers above and exits 1 if demo choice falls below the floor in `evals/floor.json`. CI runs the tests, ruff and this command on every push.

A live run needs Docker, a Gemini key and a Groq key (both free tiers). The full commands, the job post option and the HTTP service are in [docs/DESIGN.md](docs/DESIGN.md#running-it). The full results with note text stay private and gitignored. `results/eval_results.csv` is the public copy with no note text.

## Built demos

The engine sends one of two demos. Each is a standalone repo you can run in 60 seconds:

- [Call QA for voice agents](https://github.com/OWNER/REPLACE_ME_call_qa): simulated callers and a judge check an agent against a client's script before go live.
- [Invoice exception triage](https://github.com/OWNER/REPLACE_ME_invoice_exception_triage): three messy Tally or Zoho exports in, every three way match mismatch flagged and explained.

## Limits

- **The held out split was fixed after seeing results.** Only the 7 never run companies are a clean test, and only 2 of the 10 held out rows are answered so far.
- **The saved run is older than the code.** A fresh run may move the numbers.
- **The guard checks names and figures, not facts.** The demo claim check is phrase matching and missed 4 of 5 paraphrased latency claims (80%). It is a known limit, not coverage.
- **Static HTML only.** Script rendered and bot blocking sites give thin input, and the model can answer UNKNOWN.
- **Notes are drafts for a human to read.** There is no approval step in the database yet. For local use only: no auth and no rate limiting on the API, and the default database password is for local use only.

Every limit, with the rest of the design, is in [docs/DESIGN.md](docs/DESIGN.md).

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
```

`tests/test_readme_numbers.py` fails if the numbers in this README stop matching `scripts.golden_eval`.
