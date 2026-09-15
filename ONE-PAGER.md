# Kill the Quote Spreadsheet — decisions, and deliberate omissions

**Vaidant** · corrugated packaging · 5 vendors · 30 lines · 9-question questionnaire

## The interesting problem was somewhere else

Every extraction problem here is a **structuring problem declined nine days
earlier**. Of 139 vendor-line cells, **zero were comparable exactly as quoted** —
every one needed an assumption before it could sit beside another.

Forcing structure upstream is what every e-sourcing suite has tried and lost
with: a tier-3 converter with a printed rate card does not log into a buyer's
portal, and the buyer needs them more than they need the RFx. Parsing chaos is
the right **wedge** and the wrong destination. Every parse should also emit a
one-click reply link back to that vendor, pre-filled with what we just read —
*"this is what we understood, correct it here."* Less effort than replying by
email, so the next RFx returns structured without anyone adopting anything, and
it accrues the asset nobody has: vendor-confirmed unit bases, box weights and
line mappings — the exact bridge facts my system has to refuse for want of
today. **The moat isn't the parser; it's the reconciliation graph it builds.**

## Decisions

- **The conversation is the product.** A grid with a chat panel is a better
  spreadsheet; a chat stream is a transcript of stale copies. So the comparison
  renders once, **pinned**, and each turn mutates it in place. Any cell opens its
  source in a drawer — the workbook, the mail, the photograph — never a download.
- **The buyer authors the RFx, and it is not theatre.** Scope, terms, gates — in
  conversation, then a mail they approve. Every choice runs downstream: 45-day
  terms to 30 re-prices all 139 cells; un-gating ISO returns a vendor disqualified
  by an expired certificate to contention. Only the send is stubbed, and it says so.
- **Extraction writes to a relational store; the analyst queries it with typed
  tools.** Deterministic arithmetic, provenance as a foreign key, and an honest
  "where are you unsure" — because unsureness is a column. Free-form SQL is an
  escape hatch, not the path: a model writing SQL rarely errors, it returns a
  number wrong in a way nothing on screen can show.
- **The screen leads with the decision, not the table.** Cheapest, fastest,
  single-vendor, each with cost and lead time. Here ₹1,106 buys 14 days — cost
  lives in the grid, lead time in the questionnaire, and nobody joins them by
  hand. Ending at the table is why the spreadsheet survives.
- **Normalisation contains zero AI.** Eight ordered steps to landed cost. The
  moment a model does the arithmetic, nothing on screen is auditable.
- **The system never invents a number it will compare on.** Seven cells are empty
  because the incumbent priced *board* per kg and six lines are new this year, so
  no weight exists. It names the missing fact instead of estimating one.
- **Extraction and matching are separate, with separate confidence scores.** The
  dangerous failure is a *perfect* extraction on the wrong line. Extraction runs
  for real at build time and the UI says which model read which document.
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
- **Two of five adversarial defences hold**, and the matcher case is the one
  worth reading. It correctly refuses to put two rows on one buyer line and
  leaves the second unmatched — then `pipeline.run` keeps only rows with a line
  number, so the *amended* rate disappears without trace. The dangerous half of
  the defence held and the quiet half did not. Reading the code would not have
  produced that distinction; running the attack did.
- **Half the screen referred to code that did not exist.** `openTab`,
  `refreshDraft` and `renderDraftPanel` were called in four places and defined in
  none; `renderTable` still wrote to a header element I had deleted. Two
  exceptions, and between them they took out the tabs, the RFx draft card, the
  co-pilot's first reply *and the comparison grid itself* — while the page
  otherwise looked fine, because a thrown exception in a boot path leaves the
  static HTML on screen and stops. The reply had arrived and the browser simply
  could not draw it. Nothing in the Python suite could see any of this: it is all
  downstream of the API, which was answering correctly throughout.
- **The live site 500'd on the half of the product nobody had reached.** Issuing
  an RFx re-runs the pipeline, the deploy sets `EXTRACTOR=replay`, and a build
  whose recording had failed shipped with nothing to replay — so the extractor
  refused, correctly, and the API turned that into a 500. Every local check
  passed, because locally the extractor defaults to `fixture`. Refusing was
  right for the extractor; deciding what to do about the refusal belongs in the
  composition root, and there was no decision there at all.
- **The flagship interaction returned a non-answer, silently.** Asked which single
  vendor was cheapest, the analyst ran its query, got rows back, said "I will
  calculate the total" — and stopped. A malformed tool-call round-trip drew an
  empty completion, and the loop ended having said nothing. No error, no failing
  test: the only way to find it was to ask something the suggestion chips had not
  pre-baked.

## Where it stands

```
97.1% field · 97.1% unit · 100% match · 0% escape rate
0 of 139 cells comparable as quoted · 7 refused rather than estimated
29-item review queue at threshold 0.82 — a product decision, displayed
```

Every bug in the list above was found by deploying the thing and using it, and
none by a test I wrote first. That is the argument for the escape rate too, and
the reason the browser is now driven headlessly against a local server on every
change: the seam tests prove the modules meet their contracts, and the only thing
that proves the product works is working it.

Escape rate is the metric that matters: 90% accurate and catching every error
beats 98% accurate and hiding 2%, because the 98% is unverifiable without the
refusals.

## Deliberately left out

The reply-back link above. A true optimiser — 25 items is not a solver problem.
Negotiation round two, where the next rupee is. Collusion detection, should-cost
modelling, ERP integration, auth. A real mail path: the brief permits the stub,
and building it buys a checkbox rather than an argument. Voice authoring, because
speech mangles "FEFCO 0201" and "180 GSM BF22" — the exact vocabulary that proves
category knowledge.

**Known weaknesses.** The 29-item queue is too long; a queue nobody reads gets
rubber-stamped. And those figures measure everything *downstream of the read* —
matching, normalisation, the gate — against cells I deliberately made hard. Model
extraction accuracy on documents I did not generate is the number I do not have:
five real in-domain documents are wired in to get it, and I have not labelled them
yet. I'd rather say that than quote 97% as though it settled the matter.
