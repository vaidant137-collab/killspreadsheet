# The walkthrough

Eight minutes, screen and audio. The brief asks for "a recorded walkthrough of
the analyst conversation — you choose the questions worth asking," so **the
choosing is part of what is being marked.** Every question below is here because
it shows something that would not otherwise be visible.

Do not rehearse the answers. If something breaks, leave it in and say what you
would do about it — a demo where nothing goes wrong is a demo nobody believes.

| # | Beat | Time |
|---|---|---|
| 1 | The empty box — talk the RFx into existence | 0:40 |
| 2 | One decision, and a consequence you could know today | 0:50 |
| 3 | The mail in full, and the two things worth checking | 0:50 |
| 4 | Send it, and watch the round | 0:40 |
| 5 | **Questions about the read** — unsure, assumed, empty, evidence | 2:00 |
| 6 | **Questions about the money** — split, MOQ, concentration, spread | 2:00 |
| 7 | The refusal | 0:30 |
| 8 | The award memo | 0:40 |
| 9 | Provenance, and the number I do not have | 0:25 |

Steps 5 and 6 are the recording. Everything before them is setup and everything
after is the close.

---

## 0 · Before you record (30s, off camera)

- Open the URL and let the free instance wake. First load after idle takes about
  a minute; that wait on camera is dead air.
- Open **assumptions** (top right) and read the provenance line. It says one of
  three things and **each has a script** — none is a reason not to record.

  | It says | You say, at step 9 |
  |---|---|
  | `extraction by <model>` | a model read all five documents; here is which, and when |
  | `extraction by <model> — 4 of 5` | four were parsed by the model, one did not validate and fell back — **the chip counts it rather than averaging it away** |
  | `fixture path — no model read these documents` | lead with it: *the build attempts a real recorded run; today it reports the fixture path, in warning colour, because the model's output did not validate. I would rather the screen admit that than imply a model read these. Everything downstream of the read is real either way.* |

- Reload so you are on an empty chat.

---

## 1 · The empty box (40s)

No RFx exists yet. Say that the first half of this product is the part that
happens **before any vendor has replied** — which is the half most tools skip.

> **"I need to put our annual corrugated packaging out to tender. Thirty-odd
> lines, and I want it back inside two weeks."**

It drafts the **whole thing** — schedule, questionnaire, terms, gates, response
date — into the card above, and then asks for **one** decision. Say why: a
co-pilot that interviews you field by field has made you do the data entry.

## 2 · The one decision, and the honest consequence (50s)

The picker is **payment terms**, because they NPV-adjust every rate that comes
back and therefore partly decide who looks cheapest.

Point at the line under the options:

> `FY26 awarded rates on 24 of 30 lines, at 9% cost of capital`

**This is the most important twenty seconds of the first half.** An earlier build
showed *"Shakti saves you ₹445,474 against 45 days"* here — correct, computed,
traceable, and indefensible: Shakti has not replied. It told the buyer what to
ask for by reading the answers. Now the consequence is what the move does to
**your** working capital on last year's spend, and the FY26 contract is in the
repo so anyone can check it. Same for gates: *"a No disqualifies outright"*, not
who it would remove.

Pick 45 days. Say: *every rate that comes back is adjusted to this.*

## 3 · The mail, and the two things worth checking (50s)

The covering mail appears **in full**, not a summary. It is composed from the
draft, not written by the model — change the terms and it changes.

Read one line out loud:

> *"Where your rate is on a different basis — per kilogram, per hundred, per set
> — say so plainly rather than converting it; we will normalise, and we would
> rather normalise your number than guess at it."*

That is the whole thesis, addressed to the person who causes the problem.

Click **Check the line items** (30 lines, five categories, four of them honestly
empty) and **Check the vendors** (5 approved). Say: ticking a box writes straight
to the draft, **no model call** — data entry is not judgement.

## 4 · Send it (40s)

**Send to 5 vendors.** `issue_rfx` refuses without this button; re-drafting the
mail clears the approval. Say it — everyone has had a tender go out early.

Watch the **Round** panel fill: *mail sent → reply received (xlsx / pdf / docx /
photo / email) → quote read, N lines, in Nms.* Five formats, read one at a time.

Say the honest bit while it runs: **the send is stubbed and the row says so. The
times are measured, not staged** — milliseconds on the replay path, minutes on a
live model run.

---

## 5 · Questions about the read, before any question about price (2 min)

This is the part being marked. Ask the read first — a total computed over cells
you have not interrogated is a spreadsheet with better manners.

> **"Where are you unsure?"**

Twenty-nine cells below the 0.82 threshold — and **three decisions**. Say the
sentence: *a queue of twenty-nine gets rubber-stamped, so it is grouped by why
each cell is uncertain.*

- **13 cells — dimensions converted from inches.** Ganesh's rate card is in
  inches; the schedule is in millimetres. Check one and you have checked the
  convention.
- **8 cells — "rest same as last year."** Apex wrote that where a rate should be.
  The number comes from the FY26 contract attached to their reply. A pointer, not
  a price.
- **8 cells — the vendor's word is not the buyer's word.** Partition, pad, cap
  tray, fitment: dimensions and ply agree, the label does not. **The dangerous
  shape — a perfect read on the wrong line.**

Click **Show the cells** on one: nothing was hidden to make the number look
better. Then **Correct…** one value and save — the number moves on the grid and
its confidence goes to 1.0, because a correction re-runs the eight normalisation
steps. *A review queue that does not change the answer is theatre.*

> **"What did you have to assume to make these comparable?"**

FX at the rate in Meridian's own offer, freight allocated per shipment, GST
stripped from Nova's tax-inclusive quote, NPV to 45 days. Say: **zero of 139
cells were comparable exactly as quoted.**

> **"Which cells are empty, and why?"**

Seven. Apex priced *board* per kilogram; six lines are new this year and have no
unit weight on file. Say the sentence: **it is not zero, and it is not a
no-quote** — the type keeps them apart, and a test asserts no unresolved cell
carries a value.

Then open evidence on three cells, in this order:

1. **Ganesh, any line** — the photographed rate card, with the crop locator. Two
   confidence numbers: extraction and match, separately.
2. **Shakti, any line** — the workbook opens inline, both sheets, header says
   *"3 hidden rows"*. Superseded lines get hidden, not deleted. The rate is a
   formula and stays one.
3. **Apex, a line with a gap** — four lines of email, priced per kilogram.

---

## 6 · Then the commercial questions (2 min)

> **"Cheapest per line among vendors who cleared the questionnaire — and what
> does that cost versus single-sourcing?"**

Expand the collapsed computation: it says `cheapest_per_line · 30 rows`, not a
wall of SQL. Say why — **the model picks a typed tool and Python does the
arithmetic**, because a model writing SQL rarely errors, it returns a number
wrong in a way nothing on screen can show.

> **"If I take that split, does anyone fall below their minimum order?"**

Meridian's 50,000-piece slab against lines ordering 9,000. The allocator applies
the uplift and says the rate they quoted was never valid at that volume.

Open **Where the money is**:

- **13 of 30 lines carry 80% of the spend, and one layer-pad line is 28% of it.**
  Thirty lines look like thirty equal decisions. A week spread evenly across them
  is a week spent mostly on the tail.
- **Line 19 spreads 128%** between best and worst. The closest thing an RFx has
  to a measure of how contested a line was — wide spread is where a second round
  pays, narrow is the market price and arguing with it wastes the call.

Click a bar; it finds that line in the comparison. Table view underneath for
anyone the chart does not serve.

Then point at the three cards and the gap between the top two: **that difference
is what fourteen days costs.** Cost lives in the grid, lead time lives in the
questionnaire, and no spreadsheet joins them — the whole argument in one number.

## 7 · The refusal (30s)

> **"Which vendor is most reliable?"**

It declines in a block of its own: the gap in one line, then the three or four
facts it would need — delivery history, quality escapes over time, OTIF. An RFx
contains none of them.

Worth one sentence: **refusing is a tool call, not a prose apology.** Written as
prose it came out as 130 words that listed the missing facts twice and offered to
do something else instead. A refusal is an answer, so it gets the same treatment
as one — and a clean refusal is what makes the other answers worth trusting.

## 8 · The artifact that leaves the tool (40s)

**Award memo.** What was awarded, on what basis, under which assumptions, which
cells a human verified and who. Note the **Unit** column — 8.03 and 1,339.00 sit
in one rupee column and one is per piece, the other per hundred. A project whose
argument is that comparability is the hard part should not ship a comparison that
hides the unit.

Most tools in this space ship the table and leave the buyer to write this in
Word, which is exactly why the spreadsheet survives.

## 9 · Close on the honest bit (25s)

Provenance, one more time. Then the line from the one-pager: **the scorecard
measures everything downstream of the read, and extraction accuracy on documents
I did not generate is the number I do not have yet.** Five real in-domain
documents are wired in to get it; they are not labelled.

---

## If it breaks

- **The co-pilot will not answer** — key spent or provider down. The status
  counts seconds so you can see it working; it gives up honestly at 150. Click
  *"Issue the template RFx instead"* on the refusal and carry on from step 5 —
  everything there is served from the database and needs no model.
- **Blank page** — hard reload (⌘⇧R). The free instance sleeps after 15 minutes.
- **A number looks wrong** — open its evidence and find out on camera. Better
  than anything you could have scripted.

## If asked "what next?"

The **reply-back link**: every parse emits a one-click link to that vendor,
pre-filled with what we read — *"this is what we understood, correct it here."*
Less effort than replying by email, so the next RFx returns structured without
anyone adopting anything, and it accrues the asset nobody has: vendor-confirmed
unit bases, box weights and line mappings — the exact facts this system has to
refuse for want of today. **The moat is not the parser; it is the reconciliation
graph it builds.**
