# Real-world test inputs

**Correction to an earlier version of this file.** It listed photographed price
lists from other domains — a temple rate board, a taxi tariff, a fish counter —
and framed them as real-world validation. They are not. A temple rate list has
zero lines that could match a corrugated BOM, so feeding one in produces zero
matches, which is correct behaviour and proves nothing about this system. That
was a narrow vision check presented as something bigger.

What actually constitutes real-world testing here is in-domain, and most of it
already exists.

---

## Tier 1 — real, in-domain, already in the wild set

Fetched by `tools/fetch_wild_set.py`. Each one exercises a different part of the
pipeline against a document nobody here wrote.

| Document | What it actually tests |
|---|---|
| **YOJ Pack catalogue** | Relevance filtering. Real prices (₹160/sq m, ₹850/pallet) attached to a product range that is mostly honeycomb, not corrugated. Can the system find the few lines that matter among sixty that don't, and refuse to attach a catalogue price to a line it doesn't belong to? |
| **Trident PBI brochure** | "Is this even a bid?" A real corrugated brochure with no prices anywhere. The correct output is a refusal, not a parse. |
| **Pramukh brochure** | Same question, harder: a corrugated company whose brochure sells BOPP tape and stretch film. Superficially in-domain, actually irrelevant. |
| **HAL tender spec** | Real Indian buyer spec wording — layer-stack GSM, `Ntl`/`Nlt`, kg/cm², bundled sub-components. Tests the RFx side, not the vendor side. |
| **Walmart board spec** | The comparability problem at country scale: ECT-led rather than bursting-factor-led. Two real buyer specs for the same product that do not convert into one another. |

That is five real in-domain documents. **This is the real-world testing.** It was
already wired before the image detour.

## Tier 2 — the one that is actually missing

A real photographed corrugated rate card. It is almost certainly **not publicly
available**, for the same reason real quotations aren't: rate cards are
commercially sensitive and nobody publishes them.

The route that works is not a search. It is asking a supplier.

> Message three converters on IndiaMART or WhatsApp, say you are sourcing
> corrugated packaging, and ask for their rate card. Twenty minutes. What comes
> back is genuinely real, genuinely in-domain, and unarguable — and *"I asked
> three converters for rate cards and this is what actually arrived"* is a far
> better sentence in a product interview than any dataset provenance note.

Whatever arrives goes in `data/wild/`. Label 10-15 fields by hand.

## Tier 3 — optional, and honest about its scope

If a general vision smoke test is wanted — can the model read a real
photographed table of rows, labels and numbers under uncontrolled lighting at
all — one image is enough, and it should be labelled as a smoke test rather than
as validation:

**`File:Abishegam detail.jpg`** · CC BY-SA 4.0 · shot on a Samsung SM-F127G, real EXIF
https://commons.wikimedia.org/wiki/File:Abishegam_detail.jpg

It answers "does the vision path work on a real phone photo of a printed board."
It answers nothing about matching, normalisation, or comparison. Do not put it
in the demo.

---

## What to record

Not the accuracy number. **What surprised you.** "I assumed a rate card has one
unit per document" is a product finding. "94.2% field accuracy" is an
engineering artifact nobody asked for.
