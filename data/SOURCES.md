# Where this dataset comes from

Every convention below was pulled from published material, not invented. This
file exists so that each trap in the demo can be defended with a source rather
than asserted — and because several of the real conventions are messier than
anything I would have thought to make up.

---

## 1. A real tender specification — Hindustan Antibiotics Ltd, Pune

Tender `MAT/P/B-12/263`, supply of 5-ply corrugated boxes for pilot plant.
Specification wording, verbatim:

> Dimensions: **"490 X 200 X 220 Mm. (1 Ltr. Humaur)"**
> GSM: **"150/150/150/150/150 (out to In)"**
> **"Unbituminized Virgin a Grade Kraft Paper for All 5 Layers"**
> Bursting strength: **"Ntl 12 Kg/cm2"**
> **"Bursting Factor: All Layer Nlt 20"**
> Compression strength: 250 kg
> Corrugation height **"2.1 to 2.9 Mm"**, frequency **"150 to 185/m"**
> **"Staple Pins of Flat Wire as Per Is 2771 / 1977"**
> Two 3-ply B-grade plates per box, 100 GSM paper

What this changed in the dataset:

| Observation | Why it matters |
|---|---|
| GSM written as a **layer stack**, `150/150/150/150/150 (out to In)` | I had modelled a single `liner_gsm`. Real buyers specify per-layer. A vendor replying with one number has not answered the question, and a system that compares "180" against "150/150/150/150/150" is comparing nothing |
| **Three** strength measures specified at once — bursting strength in kg/cm², bursting factor, compression strength in kg | Confirms §03: strength is not one number. A vendor answering any one of the three looks compliant |
| **"Ntl"** and **"Nlt"** used in the same document, both meaning "not less than" | Real documents contain typos that a strict parser breaks on. `Ntl 12 Kg/cm2` is not a field a regex finds |
| Bursting strength in **kg/cm²**, not kPa | Indian practice differs from the TAPPI/ISO units in the international checklists. 12 kg/cm² ≈ 1,177 kPa, and nothing in either document says so |
| **"Two 3-ply plates per box"** — a sub-component inside a line item | One buyer line is really two products. A vendor who prices the plates separately has not quoted higher, they have quoted differently |
| Capacity stated as a product identity — "(1 Ltr. Humaur)" | Buyers identify boxes by what goes in them, not only by dimensions |

Source: [Supply of 5 Ply Corrugated Boxes, HAL Pune](https://www.tendersontime.com/india/details/supply-5-ply-corrugated-boxes-2166538/)

---

## 2. Live supplier listings — IndiaMART

Roughly 45 real listings for 3-ply and 5-ply boxes were read. What the market
actually does:

**Dimensions are quoted in inches at least as often as millimetres.**
`16x12x10 inches` · `12x10x8 inch` · `6x6x6 inch` · `7.00 X 5.00 X 4.25 Inches` ·
`8x6x4 inch`. Tenders specify mm. Suppliers reply in inches, rounded. Converting
`18x14x12 in` back to `450 x 350 x 300 mm` is not arithmetic, it is
unit-aware fuzzy matching against a rounding the supplier already applied.

**The same product is sold per piece by some suppliers and per kg by others.**
Star Box Factory, Noida — **₹50/Kg**. PR Paper Industries, Nagpur — **₹50/Kg**.
Shree Ganesh Packaging, Manesar — **₹60/Kg**. Everyone else quotes per piece.
This is the brief's "per box is someone else's per 100 pieces", confirmed in the
wild, in the same product category, on the same page.

**"Per Box" and "Per Piece" are used interchangeably.** AVR Reliant — ₹3/Box.
Indigo Solutions — ₹9/Box. Same unit, different word, and a naive matcher that
keys on the string treats them as different bases.

**Price dispersion inside one nominal spec is 60×.** "5 Ply corrugated box"
ranges from ₹2/piece (Crystal Enterprises) to ₹129/piece (Cheeku Technologies).
The spec everyone is quoting against is not a spec. This is the entire thesis of
the assignment, visible in one table.

**Real listings contain contradictory specifications.**
`"Double Wall 3 Ply"` — 3-ply is single wall by definition, so the listing
contradicts itself. `"Triple Wall 7 Ply"` appears in the 3-ply category. Real
vendor data is not merely unstructured, it is *wrong*, and a system that trusts
a stated spec inherits the error.

**Specification by load capacity rather than construction.** `<5 Kg` ·
`5-10 Kg` · `11-25 Kg` · `Above 45 kg`. Buyers and sellers frequently identify a
box by what it carries, not by its board.

**MOQ appears inside the description**, not as a field: `"MOQ 4000 boxes"`.

Sources: [5 Ply Corrugated Box listings](https://dir.indiamart.com/impcat/5-ply-corrugated-box.html) ·
[3 Ply Corrugated Box listings](https://dir.indiamart.com/impcat/3-ply-corrugated-box.html)

---

## 3. RFQ practice — PaperIndex procurement checklists

> **"Incoterms with named place"** — described as *"the single most important
> comparability field"*.
>
> **"Quotes missing the evidence pack are non-comparable."**
>
> *"Tooling and one-time charges [must be] separated from recurring price."*
>
> Test methods must be cited: ECT in kN/m per ISO 3037 or TAPPI T 811, burst in
> kPa. *"Different suppliers use different methods, yielding incomparable
> numbers."*

This is the landed-cost argument and the questionnaire gate, already established
industry practice rather than something the prototype invented.

Sources: [Aligning procurement and engineering — corrugated box RFQ checklist](https://www.paperindex.com/academy/aligning-procurement-and-engineering-a-shared-checklist-for-corrugated-box-rfqs/) ·
[Spec-driven RFQ template](https://www.paperindex.com/academy/the-spec-driven-kraft-paper-rfq-template-combine-technical-specs-and-commercial-terms-for-comparable-quotes/) ·
[POZI corrugated carton RFQ & QC guide](https://www.pozipackaging.com/corrugated-carton-box-specification-a-practical-rfq-qc-guide/)

---

## 4. Market price bands — and a caution about them

| Ply | Source A | Source B |
|---|---|---|
| 3-ply | ₹5 – ₹25 / piece | ₹12 – ₹30 / box |
| 5-ply | ₹25 – ₹80 / piece | ₹25 – ₹80 / box |
| 7-ply | ₹80 – ₹220 / piece | ₹70 – ₹250 / box |

**Two pages on the same publisher's site give different bands, and one says
"per piece" where the other says "per box".** One of them also states flatly
that *"pricing is quoted per piece, not per kg"* — while the IndiaMART listings
above show three suppliers quoting per kg in the same category.

Published reference prices are themselves non-comparable. That is worth saying
out loud on the call: the benchmark a buyer would reach for to sanity-check a
quote has the same defect as the quotes.

Other figures used: GSM grades 100 / 120 / 130 / 150 / 175 / 200; BF 16 / 18 /
20 / 24 / 28, with 20 BF and above for industrial; MOQ 100–200 pieces standard
and 500–1,000 for custom or printed, with a **30–50% premium below 200 pieces**.

Sources: [Corrugated box price per piece, India 2026](https://aarishapackaging.com/corrugated-box-price-per-piece-india/) ·
[Corrugated box FAQ guide 2026](https://aarishapackaging.com/corrugated-box-faq-guide/)

---

## 5. Company profile brochures — three real ones, read end to end

Vendors routinely answer an RFx with a company catalogue rather than a quote, or
attach one alongside. Three real published brochures were read to check what
that actually contains:

| | YOJ Pack | Trident PBI | Pramukh Packaging |
|---|---|---|---|
| Marketing share | ~40% | ~60% | ~70% |
| Prices | **yes** — ₹160/sq m, ₹850/pallet, ₹10/pc | none | none |
| Product range | mostly **honeycomb**, not corrugated | vague, no dimensions or grades | **BOPP tape and stretch film** |
| Certifications | — | heading present, **nothing under it** | none; only GST numbers |
| Machinery | — | full list, named models | full list with sizes (42″–72″) |
| Named clients | — | 12 | 31, incl. Ford, Godrej, Bosch |
| MOQ | inside prose: "5000-box minimum" | — | — |
| Capacity | — | "90,000+ boxes/day" **and** "18,000 MT/year" | — |

What this creates that a messy quote does not:

- **A signal-to-noise problem, not a parsing problem.** Sixty products are
  described, thirty were asked about, and most of the overlap is superficial. A
  system that tries to match everything will confidently attach a catalogue
  price to a line it does not belong to — and unlike a bad parse, that error
  looks entirely reasonable on screen.
- **Prices in units no RFx line can consume.** Per square metre. Per pallet.
  A number exists; it is not an answer.
- **A capability document masquerading as a bid.** Trident's brochure answers
  "can you make it" and never "at what price". It is not a response, however
  much it arrived in the response window.
- **Absence of evidence laid out as presence.** A section headed *"OUR
  CERTIFICATIONS"* with nothing beneath it. A buyer skimming sees a
  certifications section and moves on.
- **Capacity stated twice in units that do not convert** without a box weight
  the brochure never supplies — the same bridge-fact problem as the incumbent's
  per-kg email, in a different costume.

The rule the product has to hold: **a catalogue price is not a bid.** Finding
one is useful. Treating it as a quote is not. Surfacing it and asking is the
right behaviour, and it is a good demo moment.

Two brochures are now in the demo set, carrying contradictions against their own
vendor's quote:

- **Ganesh** advertises 7-ply export cartons at ₹96–240/box, while the rate card
  the same vendor sent states *"WE DO NOT SUPPLY 7 PLY EXPORT CARTONS OR
  SHEETS."* Brochures are printed once and go stale; rate cards are current.
- **Shakti** states a 10,000-piece minimum order in marketing prose against the
  5,000 in their own quotation. Two numbers, two documents, one vendor.

Sources: [YOJ Pack product catalogue](https://www.yojpack.com/YOJ-pack-kraft-Product-catalogue.pdf) ·
[Trident PBI brochure](https://tridentpbi.in/trident-pbi-corrugated-box-manufacturer-brochure.pdf) ·
[Pramukh Packaging brochure](https://www.pramukhpackagingindustries.com/brochure.pdf)

---

## 6. The wild set — and an honest limit

`tools/fetch_wild_set.py` downloads the real documents above, plus a real
retailer board specification and the Government of India MSME technical
reference, into `data/wild/`. They are **not** redistributed in this repository;
the script pulls them on your machine.

They are deliberately kept out of the demo set, because of a tradeoff worth
stating plainly:

> **You cannot have both a real corpus and a free gold set.** The demo documents
> are generated, which is what lets extraction be scored without anybody
> labelling anything. Real documents have no ground truth until a human writes
> one.

So the two sets have two jobs. The demo set drives the headline scorecard. The
wild set — small, hand-labelled, a few dozen fields — answers the only question
the demo set cannot: *does this work on documents we did not make?* If demo-set
accuracy is 96% and wild-set accuracy is 61%, the 96% was measuring the
renderer rather than the extractor, and that is worth knowing before a live demo
rather than during one.

---

## 7. The artifact we are killing, in its own words

A published **comparative statement of quotations** template for Indian
procurement — the exact spreadsheet the brief describes a buyer retyping for
three days. Its columns:

    Sl | Description of Item / Material | Unit | Qty |
    Vendor A Rate | Vendor B Rate | Vendor C Rate | L1 (Lowest)

with two summary rows, `SUB-TOTAL (Basic)` and
`GRAND TOTAL (incl. 18% GST)`. The lowest rate per line is highlighted; the
vendor with the lowest total becomes the recommended bidder.

The accompanying guidance says delivery period, payment terms, quotation
validity and GST/MSME status "should be recorded", and that **"freight and
discounts"** must be **"treated the same way for all vendors"**.

**Read those two sentences against the column list.** Every defect this product
exists to fix is visible in the structure of the thing itself:

| The template does this | So it cannot represent |
|---|---|
| One `Unit` column — the buyer's | That the vendor quoted per kg when you buy per piece. There is nowhere to put the vendor's unit |
| Payment terms and validity are a note, not a column | 30-day against 90-day terms. They cannot reach L1 because they are not in the arithmetic |
| Freight and discounts "treated the same way" as guidance | Anything. It is an instruction to a human with no field to hold it — a hope, not a control |
| Flat 18% GST at the bottom | A GST-inclusive quote next to a GST-extra one. They are compared as though identical |
| `L1 (Lowest)` computed on the basic rate | That the lowest basic rate is frequently not the lowest landed cost |
| No cell-level anything | Where a number came from, how confident it is, or that it is missing rather than zero |

This is worth more to the argument than any single vendor document. It is not a
strawman we built to knock down — it is what procurement teams actually use,
published as best practice, and its own instructions describe work its own
structure makes impossible.

The landed-cost basis in §03 is not an improvement on this template. It is the
minimum required for the template's own stated intent to be achievable.

Source: [Comparative statement of quotations format](https://constructionsupply.ai/comparative-statement-format)

---

## What is still synthetic, and why

The five vendor **documents** are generated, because real vendor quotations are
commercially confidential and are not published anywhere. What is real is every
*convention* they follow: the units, the notation, the abbreviations, the
contradictions, the strength measures, the dimension systems, the price bands.

The buyer side did not need to be invented at all — the HAL tender is a real
published specification and its wording is used directly.
