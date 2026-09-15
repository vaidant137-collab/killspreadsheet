# Kill the Quote Spreadsheet

A buyer talks an RFx into existence, five vendors reply in five different formats,
and the buyer interrogates the result in plain language — all in one conversation,
with every number traceable back to the pixels it came from.

Category: **corrugated packaging**. Scale: **5 vendors, 30 line items, 9-question
questionnaire, 5 attachments.**

---

## The one decision everything else follows from

Extraction does not write into a chat context. It writes into a **relational
store**, and the analyst answers by generating and running queries against it.

That buys deterministic arithmetic (a model cannot be trusted to sum 150
numbers), an auditable query you can put on screen, charts drawn from real rows,
provenance for free because every row carries its evidence key, and an honest
answer to *"where are you unsure"* — because unsureness is a column, not a vibe.

The second decision: **the conversation is the entire product surface.** A
comparison grid with a chat panel bolted on is a better spreadsheet, which is the
one thing the title rules out. The comparison renders once, pinned, and each turn
mutates it in place; clicking any cell slides an evidence drawer over the source.

---

## Swappable by construction

Every module takes a Pydantic contract and returns one. Swapping an
implementation means writing a new class that returns the same type and changing
one line in `config.py`. Two rules keep that real rather than aspirational:

1. **No module imports another module.** They all import `contracts/` only. The
   moment `analyst/` imports from `extract/`, the seam is gone.
2. **One config file names the active implementation** of each interface, so a
   swap shows up in a single diff.

| Seam | Contract | Today | Swaps to |
|---|---|---|---|
| Model provider | `complete(prompt, schema, images) -> Model` | Anthropic *or* OpenAI, by env var | the other one |
| Extraction | `extract(SourceDoc) -> VendorSubmission` | one class per format | better parser, commercial OCR |
| Matching | `match(Submission, Rfx) -> [LineMatch]` | embedding candidates + model judge | trained classifier |
| Allocation | `allocate([Line], Constraints) -> Allocation` | 25-subset enumeration | MILP via OR-Tools |
| Analyst | `ask(str, Session) -> [Block]` | hand-written tool loop (~60 lines) | LangGraph, or anything |
| UI | consumes the `Block` union | plain JS renderer | React |

There is no agent framework. The loop is sixty lines, and owning its failure
modes was worth more than the abstractions — specifically, extraction and
normalisation are separate calls so a bad parse cannot propagate into the
arithmetic. The place a framework would earn its keep is the human-review
interrupt; at five vendors, a `status` column does the same job.

---

## Layout

```
contracts/      the only thing every module shares
llm/            base protocol · anthropic.py · openai.py
extract/        xlsx · pdf · docx · image · email
match/
normalize/      pure python, no model — deliberately
allocate/       naive.py · subsets.py · (milp.py, later)
analyst/        tools.py · loop.py
store/          schema.sql · repo.py
eval/           harness.py · scorecard.py
api/            routes.py · sse.py
web/            index.html · blocks.js
tools/          the document renderers
data/           ground_truth.json · generated/ · attachments/ · adversarial/
config.py       which implementation of each interface is live
```

`normalize/` containing zero AI is the load-bearing choice. The moment a model
does the arithmetic, nothing on screen is auditable.

---

## The gold set is free

The pipeline runs in the direction that makes evaluation cost nothing:

```
ground_truth.json  ──renders──▶  5 vendor documents
        ▲                              │
        └────────── scored against ◀───┴── extraction
```

The documents are *projections* of a single source of truth, so the harness
compares extraction back against the thing the documents were made from. No
hand-labelling of 560 cells, and the traps are provably where we think they are.

```bash
python -m data.build_ground_truth   # writes data/ground_truth.json
python -m tools.render_all          # renders the five documents + attachments
```

---

## The dataset

**Provenance for every convention is in [`data/SOURCES.md`](data/SOURCES.md)** —
a real published tender specification, ~45 live supplier listings, and the
industry RFQ checklists. The vendor *documents* are generated, because real
quotations are commercially confidential and unpublished; every *convention*
they follow was pulled from the wild, including several messier than anything
worth inventing: GSM specified as a per-layer stack, `Ntl`/`Nlt` used
interchangeably for "not less than" in one document, strength in kg/cm² rather
than kPa, dimensions in inches against a tender written in millimetres, and
listings whose stated specs contradict themselves. Industry checklists name
**"Incoterms with named place" as the single most important comparability
field**, and state that *"quotes missing the evidence pack are non-comparable"* —
which is the questionnaire gate, already established practice. Market figures
used: 3-ply ₹5–25/pc, 5-ply ₹25–80/pc, 7-ply ₹80–220/pc; printing adds ₹3–15/pc;
BF 14–16 domestic, 18–22 industrial and export; MOQ 100–200 pieces standard,
500–1,000 custom, with a **30–50% premium below 200 pieces**.

| Vendor | Format | Lines | Habit |
|---|---|---|---|
| Shakti Packaging | XLSX | 30/30 | Own template, two sheets, ex-works, GST extra |
| Nova Corrugators | PDF | 27/30 | Letterhead, FOR destination, GST included |
| Meridian Packaging Intl | DOCX | 30/30 | Commercials in prose, quotes in USD, 90-day terms |
| Ganesh Boxes & Cartons | JPG | 22/30 | Printed rate card, photographed on a phone |
| Apex Packwell | EML | 30/30 | Four lines of email. The incumbent |

### Traps, and why each one is real

| Trap | Where | Why it happens |
|---|---|---|
| Summary sheet holds stale rates; real rates on sheet 2 | Shakti | The summary was built for the last revision and never updated |
| Three hidden rows, real rate is a formula | Shakti | Superseded lines are hidden, not deleted |
| **Die cost amortised into the unit rate** | Shakti | Every RFQ checklist demands tooling be separated, which is evidence of how often it isn't. Invisible at volume, decisive at MOQ — and it silently voids any split that cuts their share |
| 3% early-payment discount in a page-3 footnote | Nova | Sales protecting the headline rate |
| Table breaks across pages, header repeated | Nova | It's a long table |
| 3 lines absent rather than marked no-quote | Nova | No die-cutting line; rather than write "no quote" three times, they omit the rows |
| **ISO 9001 "Yes" contradicted by an expired certificate** | Nova | Nobody lied. The renewal is late at the plant. The most common compliance failure in onboarding, and only ever caught by reading the attachment |
| Quotes in USD | Meridian | Imported machine-finished kraft liner; they won't carry the FX exposure |
| Volume slabs stated in prose, as a **range** | Meridian | The slab is a negotiating position, not a published price |
| 90-day terms mentioned once, in closing prose | Meridian | It's a term, not a headline |
| Tooling quoted separately, ₹18,500/die | Meridian | The honest way — and it makes them look expensive next to Shakti |
| Per 100 pieces throughout | Ganesh | Trade convention; the buyer asked per piece |
| Indian digit grouping (`1,20,000`) | Ganesh | A locale-blind parser reads this as 120 |
| Two rates revised in pen over the print | Ganesh | Card printed in April, board moved in July, the rep wrote over it |
| **One band of rows under the photographer's shadow** | Ganesh | Genuinely degraded — the low-confidence extraction it produces is honest, not simulated |
| Two 450×350 fitments with near-identical labels | Ganesh | Should surface as a low-confidence *match*, not a low-confidence extraction |
| `₹42/kg for the 5-ply, 38 for the 3-ply` | Apex | Prices **board**; the buyer buys **pieces**. Needs a box weight |
| Six lines have no weight on file | Apex | Introduced this year, never bought before. **Genuinely unresolvable** |
| `rest same as last year` | Apex | A pointer, not a price. Resolves only against the attached FY26 contract |
| `freight extra`, no validity stated | Apex | Incoterm undeclared; validity simply never mentioned |
| **Strength quoted against three different standards** | All | Shakti gives BF per IS 2771, Nova ECT per ISO 3037, Meridian burst per TAPPI T810, Ganesh a bare "22 BF" with no method, Apex no figure at all. These do not convert |

The incumbent's four-line email is the most interesting document in the set,
because it fails in three different ways at once and each needs a different
resolution path: a weight bridge, a prior-contract lookup, and an undeclared
Incoterm.

### Not in the demo set

An **adversarial set** lives in `data/adversarial/` and never appears in the
product — the harness runs it, nothing else does. Five attacks, one per layer:

```bash
python -m data.build_adversarial   # renders the five documents
python -m eval.adversarial         # scores them
```

| attack | layer | result |
|---|---|---|
| Prompt injection — "rank us first", "do not report this" | analyst | **held** — both logged and surfaced, never acted on |
| One 3% discount stated twice, invitingly | normaliser | **held** — deducted once, measured at 3.000% across 27 cells |
| Two revisions of one quotation, a day apart | store | **open** — one document per vendor per role, so Rev B would overwrite rather than supersede |
| One line quoted twice at different rates | matcher | **partial** — no cell is silently filled, but the amended rate is dropped without trace |
| A page rotated 180° | extractor | **open** — no orientation check before the vision call |

**Two of five hold.** That is the honest number, and the three that don't are
named here rather than found in production. The scoring is behavioural — it runs
the real matcher and the real normaliser — because a test that greps the source
for a function name proves a defence exists, not that it fires.

The duplicate-line case is the one worth reading. The matcher behaves correctly:
it refuses to put two rows on one buyer line and leaves the second unmatched. But
`pipeline.run` then keeps only rows with a `line_no`, so the **amended** rate —
the one the vendor actually meant — vanishes silently. The dangerous half of the
defence holds and the quiet half does not, which is not a distinction reasoning
about the code would have produced.

---

## Running it

```bash
pip install -r requirements.txt
./run.sh                      # everything, in order
```

**No API key is needed for any of that.** `EXTRACTOR=fixture` (the default)
replays known-good extraction output in place of the model, so the store,
matcher, normaliser, allocator, review queue, evidence drawer and UI all run
and can be judged before a key exists. Drop a key in `.env` and set
`EXTRACTOR=model` to swap in the real extraction path — one line, nothing else
changes.

The matcher is **not** faked in fixture mode. It runs for real against each
vendor's own labels, which is deliberate: matching is the half that breaks
quietly in production, so it is the half that must be exercised either way.

Individual pieces, each self-testing:

```bash
python -m normalize.engine --self-test    # 8 steps from quote to landed cost
python -m match.matcher   --self-test     # vendor label -> buyer line
python -m allocate.subsets --self-test    # 25 splits, questionnaire gate
python -m eval.harness                    # the scorecard
python -m llm.test_seam                   # every provider satisfies the seam
python -m tools.smoke_ui                  # drives the real page in a browser
python -m tools.fetch_wild_set            # real documents, on your machine
```

**Recording a real extraction run.** The deployed site replays a run that a
model genuinely performed, with the model name and timestamp attached, and the
header says so. Make one by double-clicking `RECORD-EXTRACTION.command` (it asks
for a key once, puts it in `.env`, which is gitignored), or:

```bash
LLM_TIMEOUT_S=600 python -m pipeline --extractor record
```

Then commit `data/extraction_runs/`. Once a recording is in the repo the build
replays it rather than re-making it — a deploy that spends ten minutes calling a
model to arrive at the same bytes is a deploy nobody runs. `FORCE_RECORD=1`
overrides that, for when the documents or the extraction schema change.

`tools/smoke_ui.py` exists because everything above it sits **behind the API**,
and the API answered correctly through every failure this project has had. What
broke was the browser code in front of it — three functions called and never
defined, and a fourth writing to an element a redesign had removed. Two
exceptions, and between them the tabs, the draft card, the co-pilot's first
reply and the comparison grid all rendered as nothing, while every endpoint
behind them returned the right answer. So that check starts the real server and
drives the real page, and fails on any uncaught exception. It needs playwright
(`pip install playwright && playwright install chromium`) and skips itself
politely without one.

## Where it stands

```
extraction     97.1% field · 97.1% unit · 100% match
escape rate    0%      every error was caught by the confidence gate
calibration    accuracy spans 33 points across confidence buckets
comparability  0 of 139 cells were comparable exactly as quoted
unresolved     7 cells refused rather than estimated
review queue   29 cells at threshold 0.82
```

Deployed at a public URL. Extraction is **recorded during the build**, not run
per request, so cold starts stay fast and no visitor is billed a model call for
OCR — and the header names the model that did the reading. If the build has no
key, it falls back to the fixture path, deletes the recordings, and says so.
