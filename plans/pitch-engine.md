# Plan: pitch engine

## Goal
Given a startup's URL, gtm_agent returns a cluster, the matching demo, the deployment pain their customers have, three tailoring changes and a grounded pitch note of 150 words or fewer. A founder or FDE lead then gets a pitch about their own customers' deployment pain, with nothing generic and nothing invented.

## Decisions (the design recommendations, evaluated)
1. **Demo comes from code, not from the model.** Agreed. The model returns only `cluster` (`Literal["A","B","C","D","E","F"]`). `pitch.py` holds one table, `CLUSTER_DEMOS = {"A": "voice-agent-call-qa", "B": "invoice-exception-triage", "C": "none built", "D": "none built", "E": "none built", "F": "none built"}`, plus `CLUSTER_LABELS` for the prompt (C, D and E also name the planned demo in the label so the prompt can describe them). `demo` is still returned by `enrich()`, saved to the DB and shown by the pitch endpoint.
2. **The grounding guard is deterministic code in `pitch.py`.** Agreed.
   * Candidates: every token in `pitch_note` that starts with a capital letter or contains an inner capital or digit (`Peakflo`, `InvoiceGPT`, `HDFC`, `G2`), with possessive `'s` stripped and placeholders removed.
   * A candidate passes if its lowercase form appears as a whole word (case insensitive, `\b` boundaries) in the corpus. The corpus is title + description + about + the matched careers role phrases + company name + URL host. Anything in `ALLOWED_WORDS` also passes. That set covers sentence starters and pronouns (The, We, I, You, Your, This, Their, Our, It, Hi, Thanks), months and days, `FDE`, `AI`, `API`, `LLM`, `QA`, `SOP`, `AP`, `GST`, `CSV`, `ERP`, `Loom`, `GitHub`, `India`, `Indian`, `English`, `Hinglish`, `Tally` and `Zoho`. The last four are vocabulary from the user's own demos.
   * Known false positives: capitalised generic words that are not on the site and not allowlisted (for example `Finance` passes only if "finance" is on the site), place names, and spelling variants of the company name. Each of these costs one retry, then a NULL note.
   * Known false negatives: invented names written in lower case, invented names that happen to share a word with the site (an invented "Flow Cloud" passes if "flow" and "cloud" are both on the site, because each token is checked on its own), and invented numbers or claims ("cut errors by 40%"). It guards names, not facts.
   * On any violation (grounding or style) `enrich()` calls `ask()` **exactly once more**. The retry prompt is the original prompt plus `Your previous pitch_note was rejected for: <violations>. Write every field again and fix this.`
   * **If the retry also fails** (or returns nothing), the structured fields are kept, `pitch_note` is stored as NULL and `pitch_error` explains why, and the job still finishes `done`. Why: cluster, demo, customer_pain and tailoring are still useful, and a failed job would throw away a scrape and two LLM calls for one bad paragraph. Also, the pitch endpoint already needs a "no pitch" path for old rows.
3. **Migration.** Agreed. `schema.sql` keeps the `CREATE TABLE IF NOT EXISTS` block exactly as it is. After it come one `ALTER TABLE companies ADD COLUMN IF NOT EXISTS ...;` per new column. Every new column is nullable with no default, and the existing `create_tables()` startup hook runs it. New columns: `cluster TEXT`, `cluster_reason TEXT`, `demo TEXT`, `customer_pain TEXT`, `tailoring TEXT[]`, `pitch_note TEXT`, `pitch_error TEXT`, `careers_url TEXT`, `hiring_fde BOOLEAN`. `TEXT[]` maps straight to a Python list in psycopg, so no JSON wrapper is needed. Proof: a pytest that parses `schema.sql` (no server) plus `scripts/check_migration.py`, run against the local Postgres 16 in the sandbox. That script works only inside a throwaway `migration_check` schema, so it can never touch a real `companies` table.
4. **Careers page.** Agreed, with two choices.
   * `find_careers_url` mirrors `find_about_url`. It matches href or link text containing `career`, `jobs`, `join us`, `join-us`, `work with us` or `work-with-us`. It fetches with the same headers, `follow_redirects=True` and `timeout=10`.
   * The role keywords are matched on lowercased page text with hyphens turned into spaces: `forward deployed`, `solutions engineer`, `solution engineer`, `solutions architect`, `solution architect`, `deployment engineer`, `customer engineer`, `implementation engineer`. `hiring_fde` is three valued: `True` (a keyword was found), `False` (the page was read and had none), `None` (no link, fetch failed, or the page had no text, which is common for ATS pages rendered in JavaScript). Storing `False` for an unreadable page would be a lie.
   * The prompt gets one hiring signal line with the matched phrases, not the raw careers text. Careers pages are mostly benefits and locations, which add noise and widen the grounding corpus for no gain.
5. **Existing flow.** `normalise_url` is not touched. `ask_gemini` cooldowns and the `PROVIDERS` order are not touched. `ask_groq` also catches `pydantic.ValidationError` and returns `(None, None)`, because the bigger schema makes a bad Groq answer more likely and today that would crash the job. `enrich()` reads careers keys with `site.get(...)`, so the old site dict shape still works. Old rows with NULL new columns serialise fine in `GET /companies`. The pitch endpoint returns 404 with a clear detail.
6. **Schema compatibility.** `Company` stays flat: no nested models, so there are no `$defs` or `$ref`. `tailoring: list[str] = Field(min_length=3, max_length=3)`. Gemini gets the pydantic class as it does today (google-genai supports enum and array item limits). Groq gets `strict_schema(Company)`, a small recursive helper. It sets `additionalProperties: false` and `required` = every property at every object level, and it strips `minItems`/`maxItems`, because Groq strict mode support for them is unconfirmed. Pydantic still enforces exactly 3 on parse. Validated offline by `test_strict_schema_*` and `test_gemini_config_accepts_company_schema`. Validated live only by the manual run in T6 with `--provider gemini` and `--provider groq` (see Risks).
7. **Pitch note style checks** (`check_pitch_note` in `pitch.py`, pure code): `len(note.split()) <= 150`. No character from `- ‐ ‑ ‒ – — ― −`. The last line that is not blank contains `[LOOM_URL]` and ends with `[REPO_URL]`. The prompt asks for that last line as `Loom: [LOOM_URL] Repo: [REPO_URL]`. British English and "conclusion first, then 2 or 3 reasons" cannot be checked mechanically. They are covered in the prompt only.
8. **Real run.** No API keys exist in the sandbox, so `scripts/real_run.py` is a manual check. It calls `enrich()` directly (no DB write) and prints the full JSON and the rendered markdown. It runs inside the worker container, which already has `.env` and Redis. No acceptance criterion depends on it.

## Acceptance criteria (machine checkable, no network, no keys)
- [ ] AC1: `uv run pytest` exits 0. The existing tests in `test_scrape.py`, `test_enrich.py` and `test_worker.py` still pass, with fixtures updated only where `Company` gained fields.
- [ ] AC2: `uv run ruff check .` prints `All checks passed!`
- [ ] AC3: `uv run pytest tests/test_pitch_engine.py -k "ap_automation and cluster_b"` passes. With `ask` mocked to return cluster B for the AP automation fixture, `enrich()` returns `demo == "invoice-exception-triage"`.
- [ ] AC4: `uv run pytest tests/test_pitch_engine.py -k "voice and cluster_a"` passes. Cluster A gives `demo == "voice-agent-call-qa"`.
- [ ] AC5: `uv run pytest tests/test_pitch_engine.py -k "guard"` passes. An invented product name is rejected and `ask` is called exactly 2 times. A grounded note is accepted with 1 call. Two bad notes give `pitch_note is None`, `pitch_error` is set, the structured fields are kept and `error is None`.
- [ ] AC6: `uv run pytest tests/test_schema.py` passes. Every new column has an `ADD COLUMN IF NOT EXISTS` line, none is `NOT NULL`, and the old `CREATE TABLE` columns are unchanged.
- [ ] AC7: `uv run pytest tests/test_main.py` passes. `GET /companies/{id}/pitch` returns 200 `text/markdown` for a row with a note. It returns 404 `"Company not found"` for no row, and 404 with a detail starting `No pitch for this company` for a NULL note.
- [ ] AC8 (sandbox integration, outside pytest): `DB_URL=<local pg16 url> uv run python -m scripts.check_migration` prints `MIGRATION OK` as its last line. It applies the old schema, inserts a row, then applies `schema.sql` twice, the same way `create_tables()` does. The row survives with NULL new columns.
- [ ] AC9: `grep -c "GET /companies/{company_id}/pitch" README.md` is at least 1. `python -c "import pathlib,re;t=pathlib.Path('README.md').read_text();assert not re.search('[–—]',t)"` exits 0.
- [ ] AC10 (manual, pending keys): the user runs the T6 command on `peakflo.co` and `cekura.ai` and pastes the output. The report says plainly that live outputs are pending until keys are supplied.

## Tasks

### T1 `pitch.py`: mapping, style check, grounding guard, markdown (pure functions)
Owns: `pitch.py`, `tests/test_pitch.py`. Write the tests first.
* `CLUSTERS`, `CLUSTER_LABELS`, `CLUSTER_DEMOS`, `LOOM`, `REPO` placeholders, `ALLOWED_WORDS`.
* `check_pitch_note(note) -> list[str]`, `ungrounded_names(note, corpus) -> list[str]`, `pitch_violations(note, site) -> list[str]` (both checks), `render_pitch_markdown(row) -> str`.
* The markdown is `# Pitch for {name}`, then `Cluster`, `Demo`, `Hiring FDE` lines, `## Note` with the note, then `## Tailoring` with 3 bullets.
* No imports from `enrich` (keeps the API clients out).

Tests: `test_cluster_demos_cover_every_cluster`, `test_style_rejects_151_words`, `test_style_rejects_each_dash_character` (parametrised over the 8 characters), `test_style_requires_placeholders_on_last_line`, `test_style_accepts_valid_note`, `test_ungrounded_flags_invented_product`, `test_ungrounded_allows_site_words_case_insensitive`, `test_ungrounded_allows_allowlist_and_placeholders`, `test_ungrounded_strips_possessive`, `test_render_markdown_contains_note_and_tailoring`.
AC: `uv run pytest tests/test_pitch.py` passes. `uv run ruff check pitch.py tests/test_pitch.py` is clean.

### T2 `scrape.py`: careers page
Owns: `scrape.py`, `tests/test_scrape.py`.
* `find_careers_url(soup, base_url)`, `get_careers_text(url)` (all page text, capped at 20000 characters), `find_fde_roles(text) -> list[str]`.
* `get_description` gains the keys `careers_url`, `hiring_fde` and `fde_roles` in every return path (the error paths give `None`, `None`, `[]`).
* Network is mocked by monkeypatching `scrape.httpx.get` with a fake response.

Tests: keep every existing `normalise_url` case. Add `test_find_careers_url_matches_href_and_text`, `test_find_careers_url_skips_anchors`, `test_find_fde_roles_matches_hyphenated_forward_deployed`, `test_find_fde_roles_empty_for_unrelated_jobs`, `test_get_description_sets_hiring_fde_true_false_none` (three fake pages), `test_get_description_error_paths_have_careers_keys`.
AC: `uv run pytest tests/test_scrape.py` passes and ruff is clean.

### T3 Migration
Owns: `schema.sql`, `tests/test_schema.py`, `scripts/check_migration.py`.
* The `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` lines as in Decision 3.
* `check_migration.py` sets the search path to a throwaway `migration_check` schema, uses an embedded copy of the old schema, runs `schema.sql` text in one `execute` twice, asserts, prints `MIGRATION OK` and drops the schema.

Tests: `test_schema_adds_every_new_column_idempotently`, `test_schema_new_columns_are_nullable`, `test_schema_create_table_block_unchanged`.
AC: AC6 and AC8. If no local server is running, start one in the scratchpad with `initdb` and `pg_ctl` and paste the output.

### T4 `enrich.py`: schema, prompt, demo mapping, guard and retry
Owns: `enrich.py`, `tests/test_enrich.py`, `tests/test_pitch_engine.py`, `tests/test_worker.py` (only the `RESULT` fixture, because `Company` gains required fields).
* `Company` gains `cluster`, `cluster_reason`, `customer_pain`, `tailoring`, `pitch_note`.
* Add `strict_schema()`, used by `ask_groq`. `ask_groq` also catches `ValidationError`.
* The prompt lists the clusters A to F with labels. It asks for `cluster_reason` to quote the site and for exactly 3 tailoring changes (sample data, persona names, terminology). It gives the pitch rules (British English, 150 words at most, no hyphens or dashes, conclusion first then 2 or 3 reasons, name only products and customers in the text above, final line `Loom: [LOOM_URL] Repo: [REPO_URL]`) and the hiring signal line.
* `result()` gains `demo`, `pitch_note`, `pitch_error`, `careers_url`, `hiring_fde`.
* `tests/test_pitch_engine.py` holds two hand written fixed site dicts shaped like the new `get_description` output, both clearly fictional and labelled synthetic. `AP_SITE` is in the style of Peakflo, an AP automation company for finance teams. `VOICE_SITE` is in the style of Cekura, testing and monitoring for voice agents, with `hiring_fde=True`.

Tests: `test_ap_automation_site_maps_cluster_b_to_invoice_exception_triage`, `test_voice_site_maps_cluster_a_to_voice_agent_call_qa`, `test_prompt_contains_scraped_text_clusters_and_hiring_signal`, `test_guard_rejects_invented_product_and_retries_once`, `test_guard_accepts_grounded_note_without_retry`, `test_guard_stores_null_note_and_pitch_error_after_second_failure`, `test_guard_keeps_first_answer_when_retry_returns_nothing`, `test_strict_schema_sets_additional_properties_false_and_all_required`, `test_strict_schema_cluster_is_enum_and_tailoring_is_string_array`, `test_gemini_config_accepts_company_schema` (builds `types.GenerateContentConfig` offline), `test_ask_groq_returns_none_on_invalid_json` (fake `groq_client`). The existing `test_enrich_*` and `test_ask_*` tests stay, with fixtures and the exact dict assertion updated for the new keys.
AC: AC3, AC4, AC5, and full `uv run pytest` and ruff are clean.

### T5 `worker.py` and `main.py`: save and serve
Owns: `worker.py`, `main.py`, `tests/test_worker.py`, `tests/test_main.py`.
* `save()` inserts the 9 new columns from `result` (`pitch_note` comes from `result["pitch_note"]`, never from `company.pitch_note`).
* `GET /companies/{company_id}/pitch` returns `Response(render_pitch_markdown(row), media_type="text/markdown")`.
* The 404 details are `Company not found`, `No pitch for this company: <pitch_error>`, and `No pitch for this company: it was enriched before the pitch engine existed`.

Tests: update the existing `test_save_*` param tuples and add `test_save_writes_pitch_fields`. `tests/test_main.py` uses `fastapi.testclient.TestClient(main.app)` without the context manager, so lifespan and the DB are skipped, and a fake `psycopg.connect`. It covers `test_pitch_returns_markdown`, `test_pitch_404_unknown_company`, `test_pitch_404_null_note_with_pitch_error`, `test_pitch_404_old_row_without_pitch_fields`, and `test_get_companies_ok_with_null_new_columns`.
AC: AC7, and full `uv run pytest` and ruff are clean.

### T6 Docs, image, manual real run
Owns: `README.md`, `Dockerfile`, `scripts/real_run.py`.
* `Dockerfile` COPYs `pitch.py` and `scripts/`.
* `.env.example` and `uv.lock` already exist on this branch (committed on claude/fresh-clone). T6 does not touch them.
* `real_run.py` takes URLs and `--provider gemini|groq|all` (it sets `enrich.PROVIDERS`). It prints the JSON and the markdown. It warns when `pitch_note` is NULL.
* README: new fields, the pitch endpoint with an example, the cluster table, the guard and what happens when it fails, the new limits (guard checks names not facts, British English is checked by prompt only, careers pages rendered in JavaScript give `hiring_fde: null`, old rows have no pitch and there is no re-enrich), and how to run the migration check.

Manual command for the user (with their own `.env`):
```
docker compose up -d --build
docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run peakflo.co cekura.ai
docker compose run --rm worker /app/.venv/bin/python -m scripts.real_run --provider groq peakflo.co
```
AC: AC9, `uv run python -m scripts.real_run --help` exits 0, and full pytest and ruff are clean. The report must say: "Live outputs on peakflo.co and cekura.ai are pending until the user runs the command above with their keys."

## Task table
| id | title | files owned | depends on | group |
|----|-------|-------------|------------|-------|
| T1 | pitch.py: cluster map, style check, grounding guard, markdown | `pitch.py`, `tests/test_pitch.py` | none | A |
| T2 | Careers page scrape and FDE role detection | `scrape.py`, `tests/test_scrape.py` | none | A |
| T3 | Safe migration plus checks | `schema.sql`, `tests/test_schema.py`, `scripts/check_migration.py` | none | A |
| T4 | LLM schema, prompt, demo mapping, guard with one retry | `enrich.py`, `tests/test_enrich.py`, `tests/test_pitch_engine.py`, `tests/test_worker.py` (fixture only) | T1, T2 | B |
| T5 | Save new fields, pitch endpoint | `worker.py`, `main.py`, `tests/test_worker.py`, `tests/test_main.py` | T1, T3, T4 | C |
| T6 | README, Dockerfile, real run script | `README.md`, `Dockerfile`, `scripts/real_run.py` | T5 | D |

T1, T2 and T3 can genuinely run in parallel, because their files are disjoint. Run them one at a time anyway if the Pro plan rule applies. T4, T5 and T6 are sequential. `tests/test_worker.py` is in T4 and T5, which never run together. Commit locally on `claude/pitch-engine` after each task. No task pushes.

## Risks
| risk | cheapest experiment to kill it |
|------|-------------------------------|
| Groq strict mode rejects the schema (enum, array, or a property that is missing from `required`) | `real_run --provider groq peakflo.co` with keys: one call |
| Gemini mangles `Literal` or array limits in `response_schema`, so `parsed` is None every time | `real_run --provider gemini cekura.ai`: one call |
| Guard false positives make most real notes NULL | Run both real URLs and count retries in the log. If more than 1 of 2 fails, widen `ALLOWED_WORDS` |
| psycopg will not run several statements in one `execute` | AC8 (`check_migration.py`) on local pg16 |
| The model picks the wrong cluster (the tests mock it, so they prove only the mapping) | The real run on peakflo.co (expect B) and cekura.ai (expect A) |

## Open questions for the user
1. Demo names: should the code use `voice-agent-call-qa` and `invoice-exception-triage` (your names) or the folder names `call-qa` and `exception-triage`?
2. For clusters C to F, `demo` is "none built". Should the note then pitch the closest built demo, or skip the repo line? The current plan keeps both placeholders and lets the note pitch the approach.
3. Should the allowlist include `Tally`, `Zoho` and `Hinglish` (your demo vocabulary), even when the target's site does not mention them?
4. Rows enriched before this change have no pitch and there is no re-enrich. Do you want `POST /enrich?refresh=true` in a later slice?
5. The guard checks only `pitch_note`. `tailoring` and `customer_pain` could still invent names. Is that acceptable for a first slice?

## Ledger
<!-- /ship appends one line per finished task: id, branch, reviewer verdicts, fix rounds used -->
- T1, task/T1, review 1 CHANGES NEEDED (labels, None, Unicode), review 2 APPROVED, 1 fix round, merged d253758, 60 tests pass.
- T2, task/T2, review 1 APPROVED, 0 fix rounds, merged 73e124e, 77 tests pass. Nice to have parked: skip mailto/tel/javascript hrefs in find_careers_url, catch httpx.InvalidURL, parametrize one test.
- T3, task/T3, review 1 APPROVED, 0 fix rounds, merged 753c871, 80 tests pass, MIGRATION OK against local pg16 (reviewer reran it). Nice to have parked: finally block drops a pre-existing migration_check schema, comment on search_path.
- T4, task/T4, review 1 CHANGES NEEDED (rejected note leaked via result company, scraped text not delimited), review 2 APPROVED, 1 fix round, merged 5a24e3c, 115 tests pass. Parked: out of range cluster test, split guard helper, BUILT_DEMOS can drift from CLUSTER_DEMOS.
