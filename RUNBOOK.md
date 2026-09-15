# The walkthrough

Eight minutes. The brief asks for "a recorded walkthrough of the analyst
conversation — you choose the questions worth asking," so the choosing is part of
what is being marked. Every question below exists to show something that would
not be visible otherwise.

Record the screen with audio. Do not rehearse the answers — if something breaks,
leave it in and say what you would do about it. A demo where nothing ever goes
wrong is a demo nobody believes.

---

## 0 · Before you hit record (30 seconds)

- Open the URL and let the free instance wake up. First load after an idle period
  takes about a minute; that wait on camera is dead air.
- Look at the header chip. It will say one of three things, and **each has a
  script** — none of them is a reason not to record.

  **"extraction by \<model\>"** — a model read all five documents during the
  build. Say so at step 9 and move on.

  **"extraction by \<model\> — 4 of 5 documents"** — better material than a
  clean pass, actually. Say: *four were parsed by the model; one did not
  validate and fell back, and the chip counts it rather than averaging it away.*

  **"fixture path — no model read these documents"** — do not hide it, lead with
  it at step 9 instead of closing with it:

  > *The build attempts a real recorded extraction run on every deploy, per
  > document. Today it reports the fixture path, in warning colour, because the
  > model's output did not validate against the schema. I would rather the
  > screen admit that than imply a model read these documents. The chip existing
  > is the point — everything downstream of the read is real either way.*

  That is a stronger answer than a green chip you cannot explain.
- Reload once so you are on an empty chat.

---

## 1 · The empty box (40s)

Start on the empty chat and say what it is: no RFx exists yet, and the first half
of this product is the part that happens before any vendor has replied.

> **"I need to put our annual corrugated packaging out to tender. Thirty-odd
> lines, and I want it back inside two weeks."**

Let the co-pilot propose. It drafts the **whole** RFx first — schedule,
questionnaire, terms, vendor list — and the card appears in the pinned slot above
rather than in the chat. Say why: a co-pilot that interviews you for six turns
before showing anything has made you do the work it was supposed to do.

Then open **Item master** and **Vendors** for fifteen seconds each. Two things to
say, quickly:

- Five categories, one of them loaded, four saying *no data available*. This is
  one category in a buyer's catalogue, not a demo with the answer hardcoded.
- Ticking a line writes straight to the draft with **no model call**. Data entry
  is not judgement, and a co-pilot that occasionally mis-ticks one of thirty
  boxes is strictly worse than a checkbox. The model is for the decisions.

## 2 · The decision that decides the answer (60s)

> **"What should I gate on, and what would that cost me?"**

This is the question worth asking. Gating is buyer policy, not software
behaviour. What comes back is a list you click, and **each option carries what it
would cost** — *"disqualifies 2 of 5"*. Say the important part out loud: those
consequences are computed in Python from the live questionnaire answers and
handed to the model as data. The model names the decision; it never writes the
number. A consequence a model wrote from memory is a number the buyer would act
on and nobody could check. Then:

> **"Gate on ISO and on quality escapes. 45-day terms."**

Say the line out loud while it renders: *every rate that comes back is
NPV-adjusted to these terms, so the terms I just set decide who looks cheapest.*

## 3 · Issue it (40s)

> **"Draft the mail and send it."**

Read the stub note on screen rather than glossing it: approving does not send
mail, the SMTP path is stubbed, and the five replies are documents that already
exist. Say it plainly. Then watch the responses land.

## 4 · The decision, before the table (50s)

The three cards render first. Point at the gap:

```
Cheapest   ₹113,012,220   35 days
Fastest    ₹113,013,326   21 days
```

**₹1,106 buys you fourteen days.** Cost lives in the grid, lead time lives in the
questionnaire, and no spreadsheet joins them — that is the whole argument in one
number.

## 5 · The ugly edges (2 min) — the part they are actually marking

> **"Where are you unsure?"**

Twenty-nine cells at threshold 0.82. Open one review card and say why the queue
being *too long* is the honest failure: a queue nobody reads gets rubber-stamped.

Then use it — click **Correct…**, change the value, save. The number moves on the
grid and its confidence goes to 1.0, because a correction re-runs the eight
normalisation steps rather than being logged and forgotten. That is the whole
trust layer in one click: a human verdict is an input, not a comment.

Then click into the evidence for three cells, in this order:

1. **Ganesh, any line** — the photographed rate card. Show the crop locator, the
   shadow band, and that extraction confidence and match confidence are separate
   numbers. The dangerous failure is a perfect read on the wrong line.
2. **Shakti, any line** — the workbook opens inline, both sheets, and the header
   says *"Rate Working · 3 hidden rows"*. Superseded lines get hidden, not
   deleted. The rate is a formula and stays a formula on screen.
3. **Apex, a line with a gap** — four lines of email, priced per kilogram against
   a buyer who buys pieces. Six lines have no weight on file, so those cells are
   empty and name the missing fact. Say the sentence: *it is not zero, and it is
   not a no-quote.*

## 6 · The question the VP actually asks (60s)

> **"Cheapest per line among vendors who cleared the questionnaire — and what
> does that cost versus single-sourcing?"**

Expand the collapsed computation. It says `cheapest_per_line · 30 rows`, not a
wall of SQL. Say why: the model picks a typed tool and Python does the
arithmetic, because a model writing SQL rarely errors — it returns a number wrong
in a way nothing on screen can show.

## 7 · The refusal (40s)

> **"Which vendor is most reliable?"**

It declines in a block of its own — the gap in one line, then the three or four
facts it would need. An RFx contains none of them. This is the most important
twenty seconds in the recording: a clean refusal is what makes the other answers
worth trusting.

Worth one sentence: refusing is a **tool call**, not a prose apology. Written as
prose it came out as 130 words that listed the missing facts twice and ended by
offering to do something else instead. Refusal is an answer, so it gets the same
treatment as one.

## 8 · The artifact that leaves the tool (40s)

Click **Award memo**. What was awarded, on what basis, under which assumptions,
which cells a human verified and who. Most tools in this space ship the table and
leave the buyer to write this in Word, which is exactly why the spreadsheet
survives.

## 9 · Close on the honest bit (30s)

Header chip, one more time: which model read which document, and when. Then say
the thing the one-pager says — the scorecard measures everything downstream of
the read, and extraction accuracy on documents you did not generate is the number
you do not have yet.

---

## If it breaks

- **Co-pilot will not answer** — the key is spent or the provider is down. Click
  *"Issue the template RFx instead"* on the refusal, carry on from step 4, and
  say what happened. Everything from step 4 on is served from the database and
  needs no model.
- **Blank page** — hard reload. The free instance sleeps after fifteen minutes.
- **A number looks wrong** — open its evidence and find out on camera. That is a
  better minute of video than anything you could have scripted.
- **The co-pilot is slow** — the status counts seconds, so you can see it working
  rather than guessing. It gives up honestly at 150 seconds; if it does, say so
  and click *"Issue the template RFx instead"*.
