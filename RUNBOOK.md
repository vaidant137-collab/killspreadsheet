# The walkthrough

Eight to nine minutes, screen and audio. The brief asks for "a recorded
walkthrough of the analyst conversation — you choose the questions worth
asking," so **the choosing is part of what is being marked.** Every question
below is here because it shows something that would not otherwise be visible.

The screen is one column. Everything is a card in it, in the order the work
happens, and nothing is behind a tab — so the walkthrough is a scroll, not a
tour.

Do not rehearse the answers. If something breaks, leave it in and say what you
would do about it — a demo where nothing goes wrong is a demo nobody believes.

| # | Beat | Time |
|---|---|---|
| 1 | Four steps, not a blank box — the schedule | 0:40 |
| 2 | Vendors, questions, gates, terms | 0:50 |
| 3 | The mail in full — read it, change it, send it | 0:50 |
| 4 | The round | 0:30 |
| 5 | **The table, then what it means** | 0:50 |
| 6 | **Questions about the read** — unsure, assumed, empty, evidence | 2:00 |
| 7 | **Round two — a gap is not an answer, it is a mail** | 1:00 |
| 8 | **Questions about the money** — split, MOQ, concentration, spread | 1:30 |
| 9 | The refusal | 0:25 |
| 10 | The memo, and the number I do not have | 0:45 |

Beats 6, 7 and 8 are the recording. Everything before them is setup.

---

## 0 · Before you record (30s, off camera)

- Open the URL and let the free instance wake. First load after idle takes about
  a minute; that wait on camera is dead air.
- Open **assumptions** (top right) and read the provenance line. It says one of
  three things and **each has a script** — none is a reason not to record.

  | It says | You say, at beat 10 |
  |---|---|
  | `extraction by <model>` | a model read all five documents; here is which, and when |
  | `extraction by <model> — 4 of 5` | four were parsed by the model, one did not validate and fell back — **the chip counts it rather than averaging it away** |
  | `fixture path — no model read these documents` | lead with it: *the build attempts a real recorded run; today it reports the fixture path, in warning colour, because the model's output did not validate. I would rather the screen admit that than imply a model read these. Everything downstream of the read is real either way.* |

- Click **start over** so you begin on an empty tender.

---

## 1 · Four steps, not a blank box (40s)

Open the page. There is one card: **What are you buying?**

Say why the product starts here rather than at a chat prompt: the first half of
this tool is the part that happens **before any vendor has replied**, and most
tools skip it. A blank box that says "tell me what you need" makes the buyer
compose a paragraph to do data entry.

The item master is loaded, all thirty lines ticked, five categories with four of
them honestly empty — *this is one category in a buyer's catalogue, not a demo
with the answer hardcoded.*

Do two things on camera:

- **Change a quantity.** Type over line 15. Say: the item master is what we
  *have* bought, not what we are buying — and a changed volume moves a line past
  or under a vendor's minimum order, so it is a commercial decision, not a
  display.
- **Add a line.** *"Shelf-ready tray, 3-ply"*, 50,000. Say: it has no price
  history, so it will come back as a gap in every column — and it will not make
  the splits infeasible, because a line nobody quoted is missing from every split
  equally.

Ticking a box writes straight to the draft, **with no model call.** Data entry is
not judgement.

**Continue with 31 lines.** The card collapses to one line with a *Change* on it.

## 2 · Vendors, questions, gates, terms (50s)

**Who are you asking** — five approved vendors, all invited. Say the one sentence
that matters: this and the schedule are the two things you cannot fix after the
quotes land.

**What do you want to know about them** — nine questions, and three already
marked **disqualifying**. Say: those three are what last year's tender gated on,
carried over rather than invented, and changeable.

Untick one question. Say: it stays unticked — it goes out asking eight, and the
mail says eight. Mark **Q9, lead time** off for a beat and read the line that
appears: *leave this out and the fastest-delivery option cannot be built, because
nobody will have told you how long they take.* Put it back.

Then **terms**, and this is the most important twenty seconds of the first half.
Click **30 days** and read the line that appears underneath:

> `about INR 249,089 a year of working capital given up · FY26 awarded rates on
> 24 of 30 lines, at 9% cost of capital`

Then click back to **45 days** — *your current terms; the FY26 contract was
written on 45 days.*

An earlier build showed *"Shakti saves you ₹445,474 against 45 days"* here —
correct, computed, traceable, and indefensible: **Shakti has not replied.** It
told the buyer what to ask for by reading the answers, which is the failure this
whole project argues against. Now the consequence is what the move does to *your*
working capital on last year's spend, and the FY26 contract is in the repo so
anyone can check it. Same for the gates: *"a No disqualifies outright"*, never
who it would remove.

## 3 · The mail — read it, change it, send it (50s)

The covering mail appears **in full**, addressed to five named companies. It is
composed from the draft, not written by a model: change the terms and it changes.

Read the asks out loud, briefly — a rate against every line **in the unit on that
line**, or their unit and the conversion factor; minimum order and any price
break; freight, quoted delivered, and the per-shipment figure if not; taxes
exclusive; validity; lead time. Say: *an earlier version asked for a rate and
nothing else, and then the landed cost quietly added freight the vendor had never
been asked about.*

Type a line into the body. It is a textarea — the buyer's wording is what goes
out, and **editing it clears the approval**, so nothing rides out on the last
one.

**Send to 5 vendors.** `issue_rfx` refuses without that button. Say it: everyone
has had a tender go out early.

## 4 · The round (30s)

The round card fills in: *mail sent → reply received (xlsx / pdf / docx / photo /
email) → quote read, N lines, in Nms.*

Say the honest bit while it runs: **the send is stubbed and the card says so on
its face. Everything after it is real work on real documents** — five formats,
read one at a time, and the times are measured rather than staged.

---

## 5 · The table, then what it means (50s)

Two cards arrive, and the order is the argument.

**The table is in the conversation**, not behind a control: thirty-one lines,
five vendor columns, every rate landed to ₹ per buyer unit. Note the **Unit**
under each quantity — 8.03 and 1,339.00 sit in the same rupee column and one is
per piece, the other per hundred. A project whose argument is that comparability
is the hard part should not ship a comparison that hides the unit.

Then **what came back, and what to do about it**: three ways to award, who is out
and why, where the money is, and four things to do on Monday in plain sentences.
Say it: *a buyer does not want a table, they want to know what to do. The table is
the evidence for the answer, not the answer.*

---

## 6 · Questions about the read, before any question about price (2 min)

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
  The number comes from the FY26 contract attached to their own reply. A pointer,
  not a price.
- **8 cells — the vendor's word is not the buyer's word.** Partition, pad, cap
  tray, fitment: dimensions and ply agree, the label does not. **The dangerous
  shape — a perfect read on the wrong line.**

Click **Show the cells** on one: nothing was hidden to make the number look
better. Then **Correct…** one value and save — the number moves in the table
above and its confidence goes to 1.0, because a correction re-runs the same eight
normalisation steps. *A review queue that does not change the answer is theatre.*

> **"What did you have to assume to make these comparable?"**

FX at the rate in Meridian's own offer, freight allocated per shipment, GST
stripped from Nova's tax-inclusive quote, NPV to 45 days. Say: **not one of the
139 cells was comparable exactly as it arrived.**

> **"Which cells are empty, and why?"**

Seven, plus the line you added. Apex priced *board* per kilogram and six lines
have no unit weight on file. Say the sentence: **it is not zero, and it is not a
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

## 7 · Round two — a gap is not an answer, it is a mail (1 min)

Scroll to **Still missing — who to write to**. This is the beat most demos do not
have.

Say it plainly: *seven cells nobody can price is the honest output of round one
and it is half a product. A buyer looking at a gap does not admire the refusal —
they write to the vendor.*

Four vendors, each with what to ask and **what answering is worth in units of the
schedule** — 366,000 units against Apex, 321,000 against Meridian. Say: that
number is what decides whether the mail is worth sending at all.

**Show the mail** on Apex — composed from the gaps, not written by a model, and
it asks for exactly the thing that is missing. Then **Send it.**

Their reply comes back and **the whole pipeline runs again on it.** The card says
what moved:

> unresolved cells **7 → 1** · qualified vendors · cells needing review

Scroll up: the table above changed, in place. Say the sentence: **a reply that
only updated a display would be the same failure as a review queue that does not
change the answer.**

If there is time, send Meridian's too — their minimum order drops from 50,000 to
9,000 and twelve lines that were never valid at our volume become valid.

---

## 8 · Then the commercial questions (1:30)

> **"Cheapest per line among vendors who cleared the questionnaire — and what
> does that cost versus single-sourcing?"**

Expand the collapsed computation: it says `cheapest_per_line · 30 rows`, not a
wall of SQL. Say why — **the model picks a typed tool and Python does the
arithmetic**, because a model writing SQL rarely errors, it returns a number
wrong in a way nothing on screen can show.

> **"If I take that split, does anyone fall below their minimum order?"**

Meridian's 50,000-piece slab against lines ordering 9,000. The allocator applies
the uplift and says the rate they quoted was never valid at that volume.

**Where is the money?**

- **13 of 30 lines carry 80% of the spend, and one layer-pad line is 28% of it.**
  Thirty lines look like thirty equal decisions. A week spread evenly across them
  is a week spent mostly on the tail.
- **Line 19 spreads 128%** between best and worst. The closest thing an RFx has
  to a measure of how contested a line was — a wide spread is where a second
  round pays; a narrow one is the market price, and arguing with it wastes the
  call.

Click a bar; it finds that line in the table. Table view underneath for anyone
the chart does not serve.

Then point at the option cards and the gap between the top two: **that difference
is what fourteen days costs.** Cost lives in the grid, lead time lives in the
questionnaire, and no spreadsheet joins them — the whole argument in one number.

## 9 · The refusal (25s)

> **"Which vendor is most reliable?"**

It declines in a block of its own: the gap in one line, then the three or four
facts it would need — delivery history, quality escapes over time, OTIF. An RFx
contains none of them.

Worth one sentence: **refusing is a tool call, not a prose apology.** Written as
prose it came out as 130 words that listed the missing facts twice and offered to
do something else instead. A refusal is an answer, so it gets the same treatment
as one — and a clean refusal is what makes the other answers worth trusting.

## 10 · The memo, and the close (45s)

**Award memo for this** — on the card you actually want, not whichever is
cheapest. What was awarded, on what basis, under which assumptions, which cells a
human verified and who. Most tools in this space ship the table and leave the
buyer to write this in Word, which is exactly why the spreadsheet survives.

Then provenance, one more time, and the line from the one-pager: **the scorecard
measures everything downstream of the read, and extraction accuracy on documents
I did not generate is the number I do not have yet.** Five real in-domain
documents are wired in to get it; they are not labelled.

---

## If it breaks

- **The co-pilot will not answer** — key spent or provider down. Nothing in beats
  1–5 needs it: the four steps, the mail, the round, the table, the summary and
  the follow-ups are all served from the database. The analyst questions in beats
  6–9 do; if it is down, click *"Issue the template RFx instead"* on the refusal
  and narrate the cards instead of asking.
- **Blank page** — hard reload (⌘⇧R). The free instance sleeps after 15 minutes.
- **A number looks wrong** — open its evidence and find out on camera. Better
  than anything you could have scripted.

## If asked "what next?"

The **reply-back link**: every parse emits a one-click link to that vendor,
pre-filled with what we read — *"this is what we understood, correct it here."*
Less effort than replying by email, so the next RFx returns structured without
anyone adopting anything, and it accrues the asset nobody has: vendor-confirmed
unit bases, box weights and line mappings — the exact facts this system has to
refuse for want of today. Round two in this build is the manual version of it.
**The moat is not the parser; it is the reconciliation graph it builds.**
