# Kill the Quote Spreadsheet

A take-home for Aerchain. A buyer talks an RFx into existence, five vendors reply
in five different formats, and the buyer interrogates the result in plain
language — with every number traceable back to the pixels it came from.

Category: corrugated packaging. 5 vendors, 30 line items, 9-question
questionnaire, 7 attachments.

## Run it

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' > .env     # optional — see below
pip install -r requirements.txt
./run.sh                                       # everything, then serves :8000
```

**No API key is needed for most of it.** `EXTRACTOR=fixture` replays known-good
extraction output, so the store, matcher, normaliser, allocator, review queue,
evidence drawer and UI all run without one. **The deploy does not use it:**
`build.sh` records a real model run at build time and the site replays that, with
the model name and timestamp in the header. Without a key the build falls back to
fixture, deletes the recordings, and the header says so.

| command | what it does |
|---|---|
| `python -m data.build_ground_truth` | writes `data/ground_truth.json` |
| `python -m tools.render_all` | renders the 5 vendor documents *from* it |
| `python -m pipeline --extractor record` | one real extraction run, saved |
| `python -m pipeline --extractor replay` | returns that recorded run verbatim |
| `python -m eval.harness` | the scorecard |
| `python -m normalize.engine --self-test` | 8 steps, quote → landed cost |
| `python -m match.matcher --self-test` | vendor label → buyer line |
| `python -m allocate.subsets --self-test` | 25 splits, questionnaire gate |
| `python -m tools.estimate_cost` | prices the real token load |
| `python -m llm.test_seam` | every provider satisfies the LLMClient seam |
| `python -m data.build_adversarial` | renders the five adversarial documents |
| `python -m eval.adversarial` | scores the five attacks |

## Rules this codebase holds to

**No module imports another module.** They all import `contracts/` only. The
moment `analyst/` imports from `extract/`, the seam is gone and swapping either
becomes a refactor instead of a config change.

**`config.py` names the active implementation of each seam**, so a swap shows up
in a single diff. Seams: model provider, extraction, matching, allocation,
analyst, UI. Four model providers have been added so far. That claim was
half-false until a deploy caught it: `structured()` lived on GeminiClient, so two
of the four had no implementation at all. `python -m llm.test_seam` now asserts
every provider satisfies the seam, because a seam nobody checks is a diagram.

**`normalize/` contains zero AI, deliberately.** The moment a model does the
arithmetic, nothing on screen is auditable.

**The analyst never does arithmetic.** Every number in every answer came from a
tool call. Typed tools (`vendor_totals`, `cheapest_per_line`, `best_split`,
`show_options`) come first and compute in Python; `run_sql` is the escape hatch,
read-only at the tool boundary rather than by convention. A model writing SQL
rarely errors — it returns a number wrong in a way nothing on screen can show.

**Extraction never sees the buyer's template.** It reads into the vendor's own
schema; matching is a separate step with its own confidence score. Hand a model
30 rows and 27 rows of data and it will invent three.

**The system never invents a number it will compare on.** Three cell states:
extracted, derived, unresolved. A test asserts no unresolved cell carries a
value. `rate = NULL` is not zero and not a no-quote — the type keeps them apart.

**Ground truth is written first; documents are rendered from it.** That is what
makes the eval gold set free rather than a labelling chore. Never edit a
generated document by hand — change `data/build_ground_truth.py` and re-render.

## Layout

```
contracts/   the only thing every module shares
llm/         base protocol + anthropic / openai / gemini / openrouter
extract/     xlsx · pdf · docx · image · email, plus fixture and record/replay
match/       vendor label → buyer line, unit-aware, global assignment
normalize/   pure python, no model
allocate/    25-subset enumeration · buyer-set gate · the three options
analyst/     tools.py · loop.py · memo.py · author.py (the RFx co-pilot)
store/       schema.sql · repo.py
eval/        harness.py — field/unit/match accuracy, escape rate, calibration
api/         FastAPI + SSE
web/         index.html — chat, pinned comparison, evidence drawer
tools/       document renderers, inline previews, cost estimator, wild set
data/        ground_truth.json · generated/ · attachments/ · SOURCES.md
```

## State

```
extraction     97.1% field · 97.1% unit · 100% match   (fixture path)
escape rate    0%     every error caught by the confidence gate
comparability  0 of 139 cells comparable exactly as quoted
unresolved     7 cells refused rather than estimated
review queue   29 at threshold 0.82
```

**Built since:** RFx authoring (`analyst/author.py` — same loop, different tools
and prompt), the decision layer (`allocate.subsets.options`), inline source
previews (`tools/doc_preview.py`), and real recorded extraction at build time.

**Not built:** the wild set in `tools/fetch_wild_set.py` is fetched but
unlabelled, so the 97% is measured only against documents this repo generated.

**Known weak:** the review queue is too long at 29; freight in the pinned
comparison assumes each vendor wins everything they quoted (the allocator
re-derives it per split).

## Context worth keeping

`data/SOURCES.md` documents where every convention in the dataset came from — a
real published tender spec, ~45 live supplier listings, three real brochures, and
a published comparative-statement template whose own column structure makes its
own instructions impossible to follow. The documents are generated; the
conventions are not invented.
