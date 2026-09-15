# Kill the Quote Spreadsheet — what I decided, and what I left out

**Vaidant** · corrugated packaging · 5 vendors, 30 lines, 9-question questionnaire, 7 attachments

---

## The interesting problem was somewhere else

I built the parser the brief asks for. I don't think the parser is the product.

Every extraction problem in this assignment is a **structuring problem that was
declined nine days earlier**. Nothing in the RFx forces a vendor to state a unit,
an Incoterm, a currency or a line code — so five vendors invented five
conventions and the intelligence budget went on reconciling them. Of 139
vendor-line cells in my dataset, **zero were comparable exactly as quoted.** Not
one. Every single one needed at least one assumption before it could sit next to
another.

The obvious conclusion — force structure upstream — is the one every e-sourcing
suite of the last twenty years reached, and it loses. A tier-3 converter with a
printed rate card and an eleven-person office does not log into a buyer's portal,
and the buyer has no leverage to make them: they need the vendor more than the
vendor needs the RFx. **Parsing chaos is the correct wedge.** Aerchain is right
about that.

But it's the wrong destination. Every parse should also emit a one-click
structured reply link back to that vendor, pre-filled with what we just read from
them: *"this is what we understood — correct it here."* Their effort is now lower
than replying by email, so the second RFx comes back structured without anyone
adopting anything. That turns extraction from a permanent cost centre into an
**onboarding ramp**, and it produces the asset nobody else has: a growing corpus
of vendor-confirmed unit bases, box weights and line mappings — exactly the
bridge facts my system currently has to refuse for want of.

**The moat isn't the parser. It's the reconciliation graph the parser builds.**

A smaller second point: the deliverable a buyer actually needs is not the
comparison, it's the **award justification** — the record that answers "why this
vendor, at this price, on what basis" when Finance asks in March. Most tools ship
the table and leave the memo to Word, which is why the spreadsheet survives. Mine
ends at a generated, provenance-backed decision record.

---

## The decisions

**The conversation is the product, not a grid with a chat panel.** A comparison
grid is a better spreadsheet, which is the one thing the title rules out. But the
brief also asks for "a *single* side-by-side comparison", and a pure chat stream
is a transcript with stale copies of the table at messages 7 and 19. So: the
comparison renders **once, pinned**, and each turn mutates it in place. Clicking
any cell slides an evidence drawer over the source. Chat drives, one canvas
mutates, one drawer opens.

**Extraction writes into a relational store; the analyst answers by writing SQL
against it.** Not a chat context. This buys deterministic arithmetic (a model
cannot be trusted to sum 150 numbers), an auditable query on screen, charts from
real rows, provenance as a foreign key rather than a feature, and an honest
answer to *"where are you unsure"* — because unsureness is a column, not a vibe.

**Normalisation contains zero AI, deliberately.** Eight ordered steps from quoted
rate to landed cost: unit basis, prior-contract lookup, currency, tax, discount,
tooling, freight, payment-terms NPV. The moment a model does the arithmetic,
nothing on screen is auditable.

**Three cell states, and the system never invents a number it will compare on.**
Extracted, derived, unresolved. Seven cells are empty tonight because the
incumbent priced *board* by the kilogram and the buyer buys *pieces*, and six of
those lines were introduced this year so no dispatch weight exists. The system
names the missing fact rather than estimating a box weight and quietly ranking
Apex fourth. A test asserts no unresolved cell ever carries a value.

**Extraction and matching are separate steps with separate confidence scores.**
An extractor never sees the buyer's template — hand a model 30 rows and 27 rows
of data and it will helpfully invent three. And the dangerous failure is a
*perfect* extraction landed on the wrong line: nothing is mis-read, the number is
plausible, and nobody finds out until goods receipt.

**No agent framework.** The tool loop is sixty lines and I wanted to own its
failure modes. Where LangGraph would earn its keep is the human-review interrupt;
at five vendors a `status` column does the same job. Every seam is a Pydantic
contract, so swapping the allocator for a real MILP, or this loop for a
framework, touches one file.

**25 combinations is a `for` loop, not a solver.** Three vendors from five is
5+10+10 = 25 splits. Enumerate and rank them exactly, in milliseconds, and every
rejected split can say why — which a solver reporting "infeasible" cannot.

---

## What testing found that reasoning didn't

The scorecard is not the point. These are:

**The questionnaire gate failed dangerously, not safely.** Quality-escape parsing
read `"1 (minor — print registration, Aug 2025)"` as **12,025 escapes** and
silently disqualified the one vendor who passes everything. A gate that errs
toward exclusion looks conservative and is not.

**Inch rounding destroys the information that separates two SKUs.** Ganesh quotes
`16X12X10` and `17X13X10`; the buyer's lines are 400×300×250 and 420×320×260 mm.
Greedy matching put both labels on one line and left the other **silently
unquoted** — and the silent half is the expensive half. Fixing it needed graded
dimension proximity plus global one-to-one assignment.

**My own eval harness was flattering the system.** It scored what the matcher
emitted rather than the gold set, so a line matched to nothing counted as
"correctly matched to nothing."

---

## Where it stands

```
extraction     97.1% field · 97.1% unit · 100% match    (recorded run, replayable)
escape rate    0%     every error was caught by the confidence gate
calibration    accuracy spans 33 points across confidence buckets
comparability  0 of 139 cells comparable exactly as quoted
unresolved     7 cells refused rather than estimated
review queue   29 cells at threshold 0.82 — a product decision, displayed
```

Escape rate is the metric that matters. A system that is 90% accurate and catches
every one of its own errors is deployable. One that is 98% accurate and hides its
2% is not, because the 98% is unverifiable without the refusals.

**The dataset is generated; every convention in it is real.** Provenance for each
is in `data/SOURCES.md`: a real published tender spec (layer-stack GSM,
`Ntl`/`Nlt` used interchangeably for "not less than" in one document, strength in
kg/cm² not kPa), ~45 live supplier listings (inches against a millimetre tender;
the same product sold per-kg by some suppliers and per-piece by others; "5 ply
box" spanning ₹2 to ₹129), and three real company brochures. Real vendor
quotations are commercially confidential and unpublished, so the documents are
projections of a single ground-truth file — which is also what makes the eval
gold set free rather than a labelling chore.

---

## Deliberately left out

- **The structured reply-back link.** The argument above, not an omission.
- **A true constrained optimiser.** The search space was 25 items. A solver would
  have been a decision made for the résumé.
- **Negotiation round two** — where the next rupee actually is, once you can compare.
- **Collusion and anomaly detection.** Real; reads as a stuffed dataset in a demo.
- **Should-cost modelling** from kraft paper indices.
- **ERP/P2P integration, auth, tenancy.** Plumbing, and the brief said stub it.
- **Voice RFx authoring.** Speech-to-text mangles "FEFCO 0201" and "180 GSM
  BF22" — the exact vocabulary that proves category knowledge. Chat, not voice.

## Known weaknesses

- **The review queue is 29 items.** Honest, and too long. A queue nobody reads
  gets rubber-stamped and the trust layer becomes theatre. The threshold is the
  lever and it is exposed, not buried.
- **The wild set is unlabelled.** The 97% is measured against documents I
  generated. Five real in-domain documents are wired in `tools/fetch_wild_set.py`
  to answer the question the demo set structurally cannot — *does this work on
  documents I didn't make?* — and I have not labelled them yet. I would rather
  say that than quote the 97% as if it settled the matter.
- **Freight is allocated assuming each vendor wins everything they quoted.** The
  allocator re-derives it per split; the pinned comparison does not.
