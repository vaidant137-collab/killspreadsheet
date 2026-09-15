# Kill the Quote Spreadsheet — decisions, and deliberate omissions

**Vaidant** · corrugated packaging · 5 vendors · 30 lines · 9-question questionnaire

## The interesting problem was somewhere else

Every extraction problem here is a **structuring problem declined nine days
earlier**. Of 139 vendor-line cells, **zero were comparable exactly as quoted** —
every one needed an assumption before it could sit beside another.

The obvious fix, force structure upstream, is what every e-sourcing suite has
tried and lost with: a tier-3 converter with a printed rate card does not log
into a buyer's portal, and the buyer needs them more than they need the RFx.
Parsing chaos is the correct **wedge** — and the wrong destination. Every parse
should also emit a one-click structured reply link back to that vendor,
pre-filled with what we just read: *"this is what we understood, correct it
here."* Lower effort than replying by email, so the next RFx returns structured
without anyone adopting anything. Extraction stops being a cost centre and
becomes an onboarding ramp — and it builds the asset nobody has: vendor-confirmed
unit bases, box weights and line mappings, the exact bridge facts my system has
to refuse for want of today. **The moat isn't the parser; it's the reconciliation
graph the parser builds.**

## Decisions

- **The conversation is the product.** A grid with a chat panel is a better
  spreadsheet. But the brief wants *one* comparison, and a chat stream is a
  transcript of stale copies — so it renders once, **pinned**, and each turn
  mutates it in place. Any cell opens its source in a drawer.
- **Extraction writes to a relational store; the analyst writes SQL against it.**
  Deterministic arithmetic, an auditable query on screen, provenance as a foreign
  key, and an honest "where are you unsure" — because unsureness is a column.
- **Normalisation contains zero AI.** Eight ordered steps to landed cost. The
  moment a model does the arithmetic, nothing on screen is auditable.
- **The system never invents a number it will compare on.** Seven cells are empty
  because the incumbent priced *board* per kg and six lines are new this year, so
  no weight exists. It names the missing fact instead of estimating one.
- **Extraction and matching are separate, with separate confidence scores.** The
  dangerous failure is a *perfect* extraction on the wrong line.
- **No agent framework; 25 splits is a `for` loop, not a solver.** Every seam is a
  Pydantic contract, so swapping either costs one file.

## What testing found that reasoning didn't

- The questionnaire gate **failed dangerously**: `"1 (minor — print registration,
  Aug 2025)"` parsed as 12,025 quality escapes and silently disqualified the one
  vendor who passes everything.
- **Inch rounding destroys what separates two SKUs.** `16X12X10` and `17X13X10`
  both landed on one line, leaving its neighbour silently unquoted — and the
  silent half is the expensive half.
- **My eval harness was flattering the system**, scoring what the matcher emitted
  rather than the gold set, so a line matched to nothing scored as correct.

## Where it stands

```
97.1% field · 97.1% unit · 100% match · 0% escape rate
0 of 139 cells comparable as quoted · 7 refused rather than estimated
29-item review queue at threshold 0.82 — a product decision, displayed
```

Escape rate is the metric that matters: 90% accurate and catching every error
beats 98% accurate and hiding 2%, because the 98% is unverifiable without the
refusals.

## Deliberately left out

The structured reply-back link (the argument above). A true optimiser — 25 items
is not a solver problem. Negotiation round two, where the next rupee is. Collusion
detection, should-cost modelling, ERP integration, auth. Voice authoring: speech
mangles "FEFCO 0201" and "180 GSM BF22", the exact vocabulary that proves category
knowledge.

**Known weaknesses.** The 29-item queue is too long; a queue nobody reads gets
rubber-stamped. The 97% is measured against documents I generated — five real
in-domain documents are wired in to answer the question my own dataset structurally
cannot, and I have not labelled them yet. I'd rather say that than quote the 97% as
though it settled the matter.
