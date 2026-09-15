# Tonight's runbook

## 1 · Make extraction real (10 minutes, ~8 cents or free)

```bash
cp .env.example .env          # paste GEMINI_API_KEY
pip install -r requirements.txt
python -m data.build_ground_truth
python -m tools.render_all
python -m pipeline --extractor record     # ← the one real run. Saves what came back.
python -m eval.harness                    # ← your real scorecard. Screenshot it.
```

If extraction throws, **do not debug it under time pressure.** Fall back to
`python -m pipeline --extractor fixture`, say on the call that the recorded run is
in the repo, and move on. The demo is identical either way.

Then serve it:

```bash
python -m uvicorn api.app:app --port 8000
```

Set `LLM_PROVIDER_ANALYST=anthropic` in `.env` if you bought the $5 of Anthropic
credit — the analyst is the half anyone watches.

---

## 2 · The recording — eight minutes, one take, mistakes left in

A polished screencast of an AI product invites exactly the suspicion the brief
warned about. One take.

**Open on the number, not the tour.** Don't explain the architecture. Say:

> "Five vendors replied in five formats. Every rate here is landed cost per
> buyer unit, on one basis. A hundred and thirty-nine cells — **zero** of them
> were comparable exactly as quoted. That's the problem, and it's why the
> spreadsheet takes three days."

### The questions, in this order

**1 · "Where are you unsure?"**
Lead with this, not with the cheapest-vendor question. It's the answer to the
brief's actual challenge, and every candidate will open with the VP's question.
Shows the review queue and the seven refused cells.

**2 · Click an unresolved cell in the Apex column.**
> "Apex priced board by the kilogram. The buyer buys pieces. For twenty-four
> lines we have a dispatch weight and can bridge it; for these six the line is
> new this year and no weight exists. So the cell is empty. It could have
> averaged a box weight and quietly ranked Apex fourth — that's the version of
> this product I didn't build."

**3 · Click a Ganesh cell → the drawer.**
The whole provenance chain in one panel: the vendor's own label in *inches*
against a millimetre tender, the match rationale, the derivation, and the pen
revision visible in the photograph at 74% extraction confidence.

**4 · "Which vendors' certifications are actually valid?"**
Nova's ISO 9001 "Yes" against a certificate that expired in March. Say the line:
*"Nobody lied. The renewal is late at the plant. It's only ever caught by reading
the attachment."*

**5 · "Cheapest per line among vendors who cleared the questionnaire — and what
does that cost versus single-sourcing?"**
The VP's question. Then the caveat that changes it: twelve lines where Meridian
is priced below their 50,000 slab, so the rate they quoted was never valid at
that volume. And the ₹1,106 finding — the third vendor buys almost nothing on
₹11.3 crore and costs a whole inbound lane.

**6 · "Which vendor is most reliable?"**
A deliberate trap for your own system. It should refuse and name what it'd need —
delivery history, quality escapes over time, OTIF. **Say out loud that you asked
it on purpose.** A product declining to answer is stronger than any answer.

**7 · "Draft the award recommendation."**
Closes on the artifact that leaves the tool, including what the record does *not*
establish.

### Close on what testing found, not on the scorecard

> "Three things I only found by running it. The questionnaire gate read
> '1 (minor, Aug 2025)' as twelve thousand quality escapes and silently
> disqualified the one vendor who passes everything — it failed toward exclusion,
> which looks conservative and isn't. Inch rounding put two labels on one line and
> left its neighbour silently unquoted. And my own eval harness was flattering the
> system. None of those came from thinking harder about the design."

---

## 3 · Send

- `ONE-PAGER.md` — the graded note. One page, as asked.
- `NOTES-APPENDIX.md` — attach only if they want depth. Don't lead with it.
- The repo (GitHub, private, add their reviewers). `data/SOURCES.md` is worth a
  line in your email: it's where every convention in the dataset came from.
- The recording.

**In the email, name the weaknesses before they find them.** The 29-item queue is
too long. The 97% is measured against documents you generated, and the real
in-domain set is wired in but unlabelled. Saying it first is the difference
between a known limit and a caught one.

---

## If something breaks

| Symptom | Do this |
|---|---|
| Extraction errors | `--extractor fixture`. Demo is identical. |
| Analyst won't answer | Comparison, drawer, queue and assumptions all work with no key. Drive those. |
| Rate limited mid-demo | `--extractor replay`. That's what recording was for. |
| Anything else | Say what it should do, show the code, move on. They asked for a prototype. |
