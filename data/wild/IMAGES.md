# Real images for the wild set

Download these by hand and drop them in `data/wild/`. All are Wikimedia Commons
files under free licences (CC BY-SA or public domain) — check the licence box on
each page and keep the attribution line.

They are here for one reason, and it is not extraction accuracy. It is that a
product decision tested only against inputs we manufactured has not been tested.
The question these answer is: **what does reality do to the assumptions?**

Ranked by how much they stress the parts of the system that matter.

---

## 1. Indian phone photo of a printed rate board — the closest real analogue

**`File:Abishegam detail.jpg`** · 3,000 × 4,000 · 2.35 MB · CC BY-SA 4.0
https://commons.wikimedia.org/wiki/File:Abishegam_detail.jpg

A printed service rate list at Sri Navabrindavanam, photographed on a Samsung
SM-F127G — the EXIF is real: 1/50 sec, f/2, ISO 50, 4.6 mm. This is the Ganesh
scenario with the category swapped: a printed board of line items and rates,
shot on a phone, in India, in a script the extractor was not tuned for.

If only one image gets labelled, make it this one.

## 2. A wholesale trader's master price list — the closest to a vendor rate card

**`File:Glavni cenik veletrgovine Merkur Peter Majdič Celje.jpg`** · 2,194 × 3,043 · 1.02 MB
https://commons.wikimedia.org/wiki/File:Glavni_cenik_veletrgovine_Merkur_Peter_Majdi%C4%8D_Celje.jpg

"Main price list of the Merkur wholesale trading company." Many line items,
trade pricing, not retail. Structurally the nearest thing on Commons to the
document a converter actually sends.

## 3. A tariff board with FOUR different units in one document

**Taxi fare board, Rhodes** — search Commons for
`Preistafel für Taxifahrten Mattes 2022-10-08` · 1,680 × 3,648
(in [Category:Pricelists](https://commons.wikimedia.org/wiki/Category:Pricelists))

Base fare, per kilometre, waiting time per hour, luggage per piece, night
surcharge. The unit-normalisation problem in miniature, in a document small
enough to label in five minutes. Worth more than its size suggests.

## 4. Large, angled, real shop lighting

**`File:Cieszyn, Regera, PSS Społem, sklep z kanapkami cieszyńskimi - cennik ryb.jpg`**
· 6,000 × 8,000 · 6.54 MB
**`File:Corona test supermarket, Heiligenstädter Straße 125, Vienna - pricelist.jpg`**
· 3,792 × 4,952 · 8.84 MB

Both are price lists photographed in situ. Uncontrolled lighting, glare,
perspective — the conditions the synthetic photo approximates.

## 5. Scanned historical print — an OCR floor test

**`File:Chemist's price list, 1878 Wellcome L0026388.jpg`** · 1,306 × 1,698 · public domain
https://commons.wikimedia.org/wiki/File:Chemist%27s_price_list,_1878_Wellcome_L0026388.jpg

Dense multi-column printed price list, 19th-century type, scanned. Useful as the
low-water mark: if this fails, say so and say why rather than hiding it.

---

## The one that costs nothing and may be worth the most

Photograph a printed rate list yourself — a hardware shop's board, a printer's
rate card, a restaurant menu, a builder's quotation. Thirty seconds, genuinely
uncontrolled, and nobody can say it was selected to flatter the system.

## How to label

Do not label everything. Pick 10-15 fields per image: the item text, the rate,
the unit, and whatever the document does that our generated set never does.
Write them into `data/wild/labels.json` in the same shape as
`ground_truth.json`, and the harness scores them alongside the demo set.

What to record is not just accuracy. Record **what surprised you** — that is the
finding, and it is the part worth putting in the one-pager.
