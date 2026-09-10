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

## What is still synthetic, and why

The five vendor **documents** are generated, because real vendor quotations are
commercially confidential and are not published anywhere. What is real is every
*convention* they follow: the units, the notation, the abbreviations, the
contradictions, the strength measures, the dimension systems, the price bands.

The buyer side did not need to be invented at all — the HAL tender is a real
published specification and its wording is used directly.
