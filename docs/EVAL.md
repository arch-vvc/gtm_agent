# Eval: what I tried, where it stopped, what is next

The engine picks a cluster (A to G) for a company, and code maps the cluster to the demo to send (A or B have a demo, the rest mean none). I measured it against 38 companies whose cluster I had labelled by hand in my own tracker before the engine existed.

Everything here is recomputed from `results/eval_results.csv` by `uv run python -m scripts.golden_eval --csv results/eval_results.csv`, and `tests/test_readme_numbers.py` fails if the README or this page drifts from that output.

## Result

```
demo choice (A, B or none): 23 of 27 answered (85%)
cluster accuracy: 16 of 27 answered (59%)   BELOW the 90% target
```

The 90% cluster target is not met. Demo choice is the headline because it is what decides what gets sent: 23 of 27 answered companies got the same demo as my label. Cluster accuracy is stricter, because it also counts a wrong cluster between two clusters that have no demo built.

Of 38 companies, 31 were run, 27 answered, 4 failed before a cluster, and 7 were never run.

## What I tried

1. A model reads the home page, the about page, a customers page and the careers page (static HTML) and answers with a cluster, a reason quoted from the site, the customer's deployment pain and three tailoring changes.
2. Code, not the model, maps cluster to demo, so a wrong demo can only come from a wrong cluster.
3. A guard in `pitch.py` checks the pitch note against the site text before it is kept.
4. One live run over the golden set with real Gemini and Groq, then scoring by script with no model call.

## Where it stopped

Cluster accuracy stopped at 59% against a 90% target. I have not tuned the prompt to chase it yet. The labels overlap (see the limits below), and a prompt tuned on 27 rows would mostly fit those rows.

Full confusion matrix, rows are my label and columns are what the engine said. The `fail` column is a company that failed before a cluster.

```
          A    B    C    D    E    F    G fail
A         7    0    0    0    1    0    0    1
B         1    3    0    0    0    1    0    1
C         1    0    1    0    1    1    0    1
D         0    0    0    1    0    2    0    0
E         0    0    1    0    2    1    0    1
F         0    0    0    1    0    2    0    0
G         0    0    0    0    0    0    0    0
```

The same table reduced to the demo that gets sent:

```
          A    B none
A         7    0    1
B         1    3    1
none      1    0   13
```

## Failure buckets

Counts come from the CSV. They add up to the 38 companies except where noted.

A) 4 failed before a cluster. Cozmo AI could not be reached. Prodigal, Blue Machines AI and Notion gave the model too little text, so it answered UNKNOWN. These are thin or script rendered sites, and the engine reads static HTML only.

B) 7 wrong clusters between clusters with no demo built (Turing, Ciroos, Neural Concept, Handshake AI, Emergent Labs, SalesPatriot, Loadsmart). They cost cluster accuracy but change nothing that gets sent.

C) 4 wrong clusters that change the demo sent: Certa (labelled B, engine said F), DevRev (C, got A), CollectWise (B, got A) and LiveKit (A, got E). These are the ones that matter.

D) 5 notes rejected by the guard (Arcesium, Fibr, Shortloop, Databricks, Happyrobot). Three were for a non breaking hyphen (U+2011), and the rest were acronyms (NAV, ACID, CFO) and title words (Chief, Officer, Ops, Manager) read as invented names. The guard has since been fixed for all of these, but the saved run predates the fix.

E) 7 labelled companies never run (Alguna, Nango, Pine Labs, Gushwork, Mactores, KushoAI, Lunar).

The 16 right clusters, 11 wrong, 4 failed and 7 not run cover the 38. Buckets B and C are the 11 wrong ones, A is the 4 failed and E the 7 not run. Bucket D overlaps with the right clusters.

## Known limits of this eval

- **The held out split was fixed after seeing results.** The golden set has 10 held out rows, but I chose them after the first run, so they do not prove generalisation. Only the 7 never run companies are a clean test, because the engine had not seen them when the split was written. Today only 2 of the 10 held out rows are answered (1 correct), so the held out number is not yet meaningful. The CI floor for held out rows only applies once at least 5 are answered.
- **The saved CSV is older than the code.** The numbers come from the live run saved at commit `fcd391e`. The guard has changed since (dashes, acronyms, title words, demo fact sheets), so a fresh run may move demo choice and the notes. I have not spent the free tier quota to re run it.
- **The demo claim check is phrase matching, so it is a known limit and not coverage.** It rejects a note that says the call QA demo measures latency when the fact sheet says it does not. In a test with 5 paraphrased latency claims it missed 4 of 5 paraphrased latency claims (80%). It catches the wording I thought of and little else.
- **Labels are one person's judgement and clusters overlap.** A company can sensibly fit two clusters, so some "wrong" answers are arguable. I did not get a second labeller.
- **27 answered rows is small.** One flipped row moves demo choice by about 4 points, which is why the CI floor sits at 0.85 and is fragile.

## What is next

1. Run the 7 never run companies and the 4 failed ones live with the current code, report the held out number on its own, and update `evals/floor.json` and the README with the commit that produced it.
2. Read the C bucket by hand and decide whether the fix is better site input (more pages, a job post) or a better cluster definition.
3. Get a second person to label a sample, to measure how much of the 59% is label noise.
4. Replace the phrase matching demo claim check with something that handles paraphrase, and measure it on the same 5 paraphrases.
