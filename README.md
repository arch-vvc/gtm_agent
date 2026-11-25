# gtm_agent

gtm_agent is a pitch engine for forward deployed engineer (FDE) outreach. You give it a startup's URL. It returns the cluster the company belongs to (A to G), the demo to send, the deployment pain the company's customers likely have, three changes to tailor the demo, and a pitch note of 150 words or fewer. A guard checks the note against the company's site text: names it cannot find on the site are flagged, and number and outcome claims are caught by pattern checks that miss some paraphrases (see [docs/EVAL.md](docs/EVAL.md)). It also reports whether the careers page lists a forward deployed or solutions engineer role.

## Results

Scored by `scripts.golden_eval` against 38 companies labelled by hand before the engine existed, from the saved live run `results/eval_results.csv` (commit `fcd391e`):

```
demo choice (A, B or none): 23 of 27 answered (85%)
```

Read it with three caveats. Counted against all 38 labelled companies it is 23 of 38 (61%), because 4 failed before a cluster and 7 were never run. Always answering "none" would score 14 of 27 (52%) on the same rows. And 27 answered rows is a small sample (95% interval roughly 66% to 94%).

Demo choice decides what gets sent, so it is the headline number. The full matrix and the scoring method are in [docs/EVAL.md](docs/EVAL.md).

## How it works

1. A model reads the home, about, customers and careers pages and picks a cluster.
2. Code maps the cluster to a demo.
3. A guard in `pitch.py` checks the note against the site text and the demo's fact sheet.
4. Every note is a draft. Approval is a manual step with `scripts/approve.py`, which re-checks the note. Nothing in the service or database enforces it, and the engine never sends anything itself.

## Run it

You need [uv](https://docs.astral.sh/uv/) and Python 3.13. Scoring and the tests need no network and no keys:

```bash
uv sync
uv run python -m scripts.golden_eval --csv results/eval_results.csv --floor-file evals/floor.json
```

CI runs the tests, ruff and this command on every push.

A live run needs Docker, a Gemini key and a Groq key (both free tiers). The full commands, the job post option and the HTTP service are in [docs/DESIGN.md](docs/DESIGN.md#running-it).

## Built demos

The engine sends one of two demos. Each is a standalone repo you can run in 60 seconds:

- [Call QA for voice agents](https://github.com/arch-vvc/voice-agent-call-qa): simulated callers and a judge check an agent against a client's script before go live.
- [Invoice exception triage](https://github.com/arch-vvc/invoice-exception-triage): three messy Tally or Zoho exports in, every three way match mismatch flagged and explained.

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
```
