"""
Builds data/ground_truth.json — the single source of truth for the whole demo.

Everything downstream is a projection of this file:
  - the five vendor documents are RENDERED from it (tools/render_all.py)
  - the eval gold set IS it (eval/harness.py)

So the traps are provably where we think they are, and extraction accuracy is
measurable without anybody hand-labelling 560 cells.

Run:  python -m data.build_ground_truth
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from contracts.quote import (
    Attachment,
    GroundTruth,
    Incoterm,
    QuestionnaireAnswer,
    QuoteBasis,
    TaxBasis,
    VendorLineQuote,
    VendorProfile,
    VendorSubmission,
    VolumeSlab,
)
from contracts.rfx import (
    BoxStyle,
    Dimensions,
    PriorContractLine,
    QuestionnaireItem,
    Rfx,
    RfxLine,
    Uom,
)

HERE = Path(__file__).parent
SEED = 20260910

# ----------------------------------------------------------------------------
# Board physics — so prices are internally consistent rather than typed by hand.
# Grounded in published Indian market practice: 3-ply Rs 5-25/pc, 5-ply
# Rs 25-80/pc, 7-ply Rs 80-220/pc; printing adds Rs 3-15/pc; BF 14-16 domestic,
# 18-22 industrial/export.
# ----------------------------------------------------------------------------

PLY_GSM = {2: 380, 3: 560, 5: 960, 7: 1380}          # total board g/m2
BOARD_RATE_PER_KG = {2: 36.0, 3: 38.0, 5: 42.0, 7: 47.0}  # the brief's own numbers
CONVERSION_PER_PIECE = {
    BoxStyle.RSC_0201: 2.20,
    BoxStyle.HSC_0203: 3.00,
    BoxStyle.DIECUT_0427: 4.50,
    BoxStyle.PAD: 0.80,
    BoxStyle.PARTITION: 1.60,
    BoxStyle.SHEET: 0.0,
}
PRINT_COST = {"plain": 0.0, "1-col flexo": 2.50, "2-col flexo": 5.50}
DIE_COST_INR = 18500.0
GST_PCT = 18.0


def blank_area_m2(line: RfxLine) -> float:
    """Board consumed per piece, including trim and flap allowance."""
    d = line.dims
    if line.style in (BoxStyle.SHEET, BoxStyle.PAD):
        return (d.length_mm * d.width_mm) / 1e6
    if line.style == BoxStyle.PARTITION:
        # a partition set is several slotted strips
        return (d.length_mm * d.width_mm * 2.4) / 1e6
    h = d.height_mm or 0
    area = ((2 * (d.length_mm + d.width_mm) + 45) * (h + d.width_mm + 35)) / 1e6
    if line.style == BoxStyle.DIECUT_0427:
        area *= 1.35  # die-cut wastes more board than a slotted box
    return area


def piece_weight_g(line: RfxLine) -> float:
    gsm = PLY_GSM[line.ply or 3]
    if line.liner_gsm:
        gsm *= line.liner_gsm / 160.0
    return blank_area_m2(line) * gsm


def base_price_inr(line: RfxLine) -> float:
    """Fair market price per buyer-UOM, before any vendor's own margin."""
    ply = line.ply or 3
    kg = piece_weight_g(line) / 1000.0
    if line.uom == Uom.KG:
        return BOARD_RATE_PER_KG[ply] + 4.5  # board rate + conversion, per kg
    price = kg * BOARD_RATE_PER_KG[ply]
    price += CONVERSION_PER_PIECE[line.style]
    price += PRINT_COST.get(line.print_spec, 0.0)
    return price


# ----------------------------------------------------------------------------
# The 30 lines
# ----------------------------------------------------------------------------

def _rsc(n, code, ply, l, w, h, gsm, bf, prt, qty, **kw):
    return RfxLine(
        line_no=n, code=code,
        description=f"Corrugated box, RSC (FEFCO 0201), {ply}-ply, {l}x{w}x{h} mm, "
                    f"{gsm} GSM liner, {bf} BF, {prt}",
        style=BoxStyle.RSC_0201, ply=ply, dims=Dimensions(length_mm=l, width_mm=w, height_mm=h),
        flute="B" if ply == 3 else "BC", liner_gsm=gsm, bursting_factor=bf,
        print_spec=prt, annual_qty=qty, uom=Uom.PIECE, **kw)


def build_lines() -> list[RfxLine]:
    L: list[RfxLine] = []
    # --- 3-ply domestic FMCG boxes (BF 14-16) --------------------------------
    L.append(_rsc(1, "CB-0201-3P-300200150", 3, 300, 200, 150, 150, 16, "plain", 240000,
                  unit_weight_g=None, food_contact=True))
    L.append(_rsc(2, "CB-0201-3P-350250200", 3, 350, 250, 200, 150, 16, "1-col flexo", 180000))
    L.append(_rsc(3, "CB-0201-3P-250200120", 3, 250, 200, 120, 140, 14, "plain", 300000,
                  food_contact=True))
    L.append(_rsc(4, "CB-0201-3P-400300200", 3, 400, 300, 200, 150, 16, "2-col flexo", 150000))
    L.append(_rsc(5, "CB-0201-3P-320240180", 3, 320, 240, 180, 150, 16, "plain", 96000,
                  food_contact=True))
    # --- 5-ply industrial boxes (BF 20-22) -----------------------------------
    L.append(_rsc(6, "CB-0201-5P-450350300", 5, 450, 350, 300, 180, 22, "2-col flexo", 120000))
    L.append(_rsc(7, "CB-0201-5P-500400350", 5, 500, 400, 350, 180, 22, "2-col flexo", 84000))
    L.append(_rsc(8, "CB-0201-5P-400300250", 5, 400, 300, 250, 180, 20, "1-col flexo", 132000))
    L.append(_rsc(9, "CB-0201-5P-600400400", 5, 600, 400, 400, 180, 22, "plain", 60000))
    L.append(_rsc(10, "CB-0201-5P-380280220", 5, 380, 280, 220, 180, 20, "plain", 108000))
    L.append(_rsc(11, "CB-0201-5P-550380320", 5, 550, 380, 320, 180, 22, "2-col flexo", 72000,
                  introduced_this_year=True))
    L.append(_rsc(12, "CB-0201-5P-300300300", 5, 300, 300, 300, 180, 20, "plain", 90000,
                  introduced_this_year=True))
    L.append(_rsc(13, "CB-0201-5P-480320280", 5, 480, 320, 280, 180, 22, "1-col flexo", 66000,
                  introduced_this_year=True))
    L.append(_rsc(14, "CB-0201-5P-420320260", 5, 420, 320, 260, 180, 22, "2-col flexo", 144000))
    L.append(_rsc(15, "CB-0201-5P-650450450", 5, 650, 450, 450, 200, 22, "plain", 48000,
                  introduced_this_year=True))
    # --- 7-ply export HSC (BF 24) --------------------------------------------
    for n, (l, w, h, prt, qty) in enumerate(
        [(600, 400, 400, "2-col flexo", 36000),
         (700, 500, 450, "1-col flexo", 24000),
         (550, 450, 400, "plain", 30000)], start=16):
        L.append(RfxLine(
            line_no=n, code=f"CB-0203-7P-{l}{w}{h}",
            description=f"Export carton, HSC (FEFCO 0203), 7-ply, {l}x{w}x{h} mm, "
                        f"200 GSM liner, 24 BF, {prt}",
            style=BoxStyle.HSC_0203, ply=7,
            dims=Dimensions(length_mm=l, width_mm=w, height_mm=h),
            flute="BC", liner_gsm=200, bursting_factor=24, print_spec=prt,
            annual_qty=qty, uom=Uom.PIECE))
    # --- die-cut mailers: Nova cannot quote these ----------------------------
    for n, (ply, l, w, h, gsm, bf, qty) in enumerate(
        [(3, 250, 180, 80, 150, 16, 60000),
         (3, 300, 220, 100, 150, 16, 45000),
         (5, 350, 250, 120, 180, 20, 36000)], start=19):
        L.append(RfxLine(
            line_no=n, code=f"CB-0427-{ply}P-{l}{w}{h}",
            description=f"Die-cut mailer (FEFCO 0427), {ply}-ply, {l}x{w}x{h} mm, "
                        f"{gsm} GSM liner, {bf} BF, 2-col flexo",
            style=BoxStyle.DIECUT_0427, ply=ply,
            dims=Dimensions(length_mm=l, width_mm=w, height_mm=h),
            flute="E" if ply == 3 else "BC", liner_gsm=gsm, bursting_factor=bf,
            print_spec="2-col flexo", annual_qty=qty, uom=Uom.PIECE,
            requires_tooling=True,
            introduced_this_year=(n in (20, 21))))
    # --- sheets, priced per kg (Ganesh has no sheet plant) -------------------
    for n, (ply, l, w, gsm, bf, kg) in enumerate(
        [(3, 1200, 900, 150, 16, 18000),
         (5, 1200, 900, 180, 20, 24000),
         (5, 1500, 1000, 180, 22, 15000),
         (3, 1000, 800, 140, 14, 12000),
         (7, 1200, 1000, 200, 24, 9000)], start=22):
        L.append(RfxLine(
            line_no=n, code=f"CS-{ply}P-{l}{w}",
            description=f"Corrugated sheet, {ply}-ply, {l}x{w} mm, {gsm} GSM liner, {bf} BF",
            style=BoxStyle.SHEET, ply=ply,
            dims=Dimensions(length_mm=l, width_mm=w),
            flute="B" if ply == 3 else "BC", liner_gsm=gsm, bursting_factor=bf,
            annual_qty=kg, uom=Uom.KG))
    # --- pads and partitions -------------------------------------------------
    L.append(RfxLine(
        line_no=27, code="CP-2P-1150950",
        description="Layer pad, 2-ply, 1150x950 mm, 140 GSM liner",
        style=BoxStyle.PAD, ply=2, dims=Dimensions(length_mm=1150, width_mm=950),
        flute="B", liner_gsm=140, annual_qty=24000, uom=Uom.HUNDRED))
    L.append(RfxLine(
        line_no=28, code="CD-3P-4CELL-450350",
        description="Partition set, 4-cell, 3-ply, to suit 450x350x300 mm case",
        style=BoxStyle.PARTITION, ply=3, dims=Dimensions(length_mm=450, width_mm=350),
        flute="B", liner_gsm=150, annual_qty=120000, uom=Uom.SET))
    L.append(RfxLine(
        line_no=29, code="CD-3P-6CELL-500400",
        description="Partition set, 6-cell, 3-ply, to suit 500x400x350 mm case",
        style=BoxStyle.PARTITION, ply=3, dims=Dimensions(length_mm=500, width_mm=400),
        flute="B", liner_gsm=150, annual_qty=84000, uom=Uom.SET))
    L.append(RfxLine(
        line_no=30, code="CT-3P-CAPTRAY-450350",
        description="Top cap and bottom tray pair, 3-ply, 450x350 mm",
        style=BoxStyle.PARTITION, ply=3, dims=Dimensions(length_mm=450, width_mm=350),
        flute="B", liner_gsm=150, annual_qty=60000, uom=Uom.SET))

    # ---- real tender conventions, applied across the schedule ---------------
    # Lifted from HAL tender MAT/P/B-12/263 (see data/SOURCES.md). Note "Ntl"
    # and "Nlt" both appear, both meaning "not less than", exactly as they do
    # in the source document. Strength is stated in kg/cm2, not the kPa the
    # international checklists assume, and no document anywhere says
    # 12 kg/cm2 is about 1,177 kPa.
    STACK = {
        2: "140/120/140 (out to In)",
        3: "150/120/150 (out to In)",
        5: "180/140/150/140/180 (out to In)",
        7: "200/150/150/150/150/150/200 (out to In)",
    }
    STRENGTH = {
        2: {"bursting_strength": "Nlt 5 kg/cm2", "bursting_factor": "All layer Ntl 14"},
        3: {"bursting_strength": "Nlt 8 Kg/cm2", "bursting_factor": "All Layer Nlt 16",
            "compression_strength": "Nlt 120 kg"},
        5: {"bursting_strength": "Ntl 12 Kg/cm2", "bursting_factor": "All Layer Nlt 20",
            "compression_strength": "Nlt 250 kg"},
        7: {"bursting_strength": "Nlt 16 Kg/cm2", "bursting_factor": "All layer Ntl 24",
            "compression_strength": "Nlt 400 kg"},
    }
    CAPACITY = {2: None, 3: "5-10 Kg", 5: "11-25 Kg", 7: "Above 45 kg"}

    for ln in L:
        ln.gsm_stack = STACK.get(ln.ply or 3)
        ln.strength_spec = dict(STRENGTH.get(ln.ply or 3, {}))
        if ln.style in (BoxStyle.RSC_0201, BoxStyle.HSC_0203, BoxStyle.DIECUT_0427):
            ln.capacity_band = CAPACITY.get(ln.ply)

    # One buyer line is really two products, exactly as in the source tender.
    by_no_tmp = {l.line_no: l for l in L}
    by_no_tmp[6].sub_components = ["Two 3-ply B-grade plates per box, 100 GSM paper"]
    by_no_tmp[6].capacity_band = "11-25 Kg (1 Ltr. Humaur pack)"

    # Bridge facts: the buyer has dispatch weights for lines they have bought
    # before, and none for the six introduced this year. That is not a gap in
    # our dataset — it is the honest state of a real procurement file, and it
    # is what makes the incumbent's per-kg quote genuinely unresolvable.
    for ln in L:
        if ln.uom in (Uom.PIECE, Uom.SET, Uom.HUNDRED) and not ln.introduced_this_year:
            ln.unit_weight_g = round(piece_weight_g(ln), 1)
    return L


QUESTIONNAIRE = [
    QuestionnaireItem(q_no=1, question="Are you ISO 9001:2015 certified? State certificate number and expiry date.", answer_type="text", gating=True),
    QuestionnaireItem(q_no=2, question="Do you hold FSC chain-of-custody certification?", answer_type="yes_no"),
    QuestionnaireItem(q_no=3, question="Do you hold BRCGS Packaging Materials certification (required for food-contact lines)?", answer_type="yes_no"),
    QuestionnaireItem(q_no=4, question="Monthly converting capacity, in tonnes.", answer_type="number"),
    QuestionnaireItem(q_no=5, question="Do you operate a second plant or documented disaster-recovery arrangement?", answer_type="yes_no"),
    QuestionnaireItem(q_no=6, question="Are you registered as an MSME (Udyam)?", answer_type="yes_no"),
    QuestionnaireItem(q_no=7, question="Number of quality escapes or recalls in the last 24 months.", answer_type="number", gating=True),
    QuestionnaireItem(q_no=8, question="State board strength rating AND the test method used (e.g. ECT per ISO 3037, or bursting factor per IS 2771).", answer_type="text", gating=True,
                      note="Method matters: ECT (kN/m) and burst (kPa / BF) do not convert into one another."),
    QuestionnaireItem(q_no=9, question="Standard production lead time in days, from PO to despatch.", answer_type="number"),
]


# ----------------------------------------------------------------------------
# Vendors
# ----------------------------------------------------------------------------

VENDORS = [
    VendorProfile(
        vendor_id="shakti", name="Shakti Packaging Pvt Ltd", city="Bhiwandi, Maharashtra",
        reply_format="xlsx", dimension_system="mm", unit_wording="Per Box", currency="INR", incoterm=Incoterm.EX_WORKS,
        tax_basis=TaxBasis.GST_EXTRA, payment_days=30, validity_days=15,
        moq_pieces=5000, freight_inr_per_shipment=42000, shipments_per_year=12),
    VendorProfile(
        vendor_id="nova", name="Nova Corrugators Pvt Ltd", city="Vasai East, Maharashtra",
        reply_format="pdf", dimension_system="mm", unit_wording="No.", currency="INR", incoterm=Incoterm.FOR_DESTINATION,
        tax_basis=TaxBasis.GST_INCLUDED, payment_days=45, validity_days=30,
        early_payment_discount_pct=3.0, early_payment_within_days=15,
        moq_pieces=3000, freight_inr_per_shipment=0.0, shipments_per_year=12),
    VendorProfile(
        vendor_id="meridian", name="Meridian Packaging International", city="Chennai, Tamil Nadu",
        reply_format="docx", dimension_system="mm", unit_wording="pc", currency="USD", incoterm=Incoterm.EX_WORKS,
        tax_basis=TaxBasis.GST_EXTRA, payment_days=90, validity_days=30,
        moq_pieces=50000, fx_rate_at_quote=87.10,
        slabs=[VolumeSlab(min_qty=50000, uplift_pct=0.0),
               VolumeSlab(min_qty=0, uplift_pct=13.5)],
        freight_inr_per_shipment=96000, shipments_per_year=12),
    VendorProfile(
        vendor_id="ganesh", name="Ganesh Boxes & Cartons", city="Ambernath, Maharashtra",
        reply_format="photo", dimension_system="inch", unit_wording="Per 100 Box", currency="INR", incoterm=Incoterm.EX_WORKS,
        tax_basis=TaxBasis.GST_EXTRA, payment_days=30, validity_days=21,
        moq_pieces=2000, freight_inr_per_shipment=38000, shipments_per_year=12),
    VendorProfile(
        vendor_id="apex", name="Apex Packwell", city="Bhiwandi, Maharashtra", incumbent=True,
        reply_format="email", dimension_system="mm", unit_wording="per kg", currency="INR", incoterm=Incoterm.FREIGHT_EXTRA,
        tax_basis=TaxBasis.GST_EXTRA, payment_days=45, validity_days=None,
        moq_pieces=5000, freight_inr_per_shipment=40000, shipments_per_year=12),
]

# Which buyer lines each vendor declines to quote, and why.
NO_QUOTE = {
    "shakti": [],
    "nova": [19, 20, 21],                       # no die-cutting line
    "meridian": [],
    "ganesh": [16, 17, 18, 22, 23, 24, 25, 26], # no 7-ply, no sheet plant
    "apex": [],
}

MARGIN = {"shakti": 0.98, "nova": 1.035, "meridian": 0.955, "ganesh": 1.015, "apex": 1.0}

QUESTIONNAIRE_ANSWERS = {
    "shakti": [
        ("IS/ISO 9001:2015, cert. QMS-4471-IN, valid to 30 Jun 2027", None, False),
        ("No", None, False), ("No", None, False), ("900", None, False),
        ("No - single plant, Bhiwandi", None, False), ("No", None, False),
        ("1 (minor - print registration, Aug 2025)", None, False),
        ("22 BF as per IS 2771", None, False), ("21", None, False),
    ],
    "nova": [
        # The questionnaire says certified. The attached certificate expired in March.
        ("Yes - ISO 9001:2015, cert. NC/QMS/2219, see attached certificate",
         "nova_iso9001_certificate.pdf", True),
        ("Yes - FSC C148820", None, False), ("Yes - BRCGS Packaging, AA grade", None, False),
        ("1400", None, False), ("Yes - second plant at Silvassa", None, False),
        ("No", None, False), ("0", None, False),
        ("ECT 32 kN/m (ISO 3037)", None, False), ("18", None, False),
    ],
    "meridian": [
        ("Yes - ISO 9001:2015, cert. TUV-IN-88214, valid to 14 Nov 2027", None, False),
        ("Yes", None, False), ("No", None, False), ("2200", None, False),
        ("Yes - Hosur unit", None, False), ("No", None, False), ("2", None, False),
        ("Bursting strength 1,400 kPa (TAPPI T810)", "meridian_test_report.pdf", False),
        ("35", None, False),
    ],
    "ganesh": [
        ("Not certified", None, False), ("No", None, False), ("No", None, False),
        ("260", None, False), ("No", None, False),
        ("Yes - Udyam-MH-19-0044821", "ganesh_udyam_certificate.pdf", False),
        ("0", None, False),
        ("22 BF", None, False),   # no test method cited at all
        ("12", None, False),
    ],
    "apex": [
        ("Yes - ISO 9001:2015, cert. AP-9001-2311, valid to 31 Dec 2026", None, False),
        ("No", None, False), ("No", None, False), ("750", None, False),
        ("No", None, False), ("Yes", None, False), ("2", None, False),
        ("Meets buyer specification", None, False),  # no value, no method
        ("15", None, False),
    ],
}

ATTACHMENTS = {
    "nova": [Attachment(filename="nova_iso9001_certificate.pdf", kind="iso9001",
                        valid_until="2026-03-31",
                        summary="ISO 9001:2015 certificate NC/QMS/2219. Expired 31 March 2026 - "
                                "contradicts the 'Yes' given at question 1.")],
    "meridian": [Attachment(filename="meridian_test_report.pdf", kind="test_report",
                            summary="Bursting strength test report, TAPPI T810, 1,400 kPa.")],
    "ganesh": [Attachment(filename="ganesh_company_profile.pdf", kind="brochure",
                          summary="Company profile. Mostly marketing; the product range "
                                  "includes honeycomb board, paper pallets, BOPP tape and "
                                  "stretch film that no RFx line asks for, priced per sq "
                                  "metre and per pallet. CONTRADICTS the rate card: "
                                  "advertises 7-ply export cartons at Rs 96-240/box while "
                                  "the rate card states they do not supply them. A "
                                  "catalogue price is not a bid."),
               Attachment(filename="ganesh_udyam_certificate.pdf", kind="msme",
                          valid_until="2027-08-31",
                          summary="Udyam MSME registration certificate.")],
    "shakti": [Attachment(filename="shakti_company_profile.pdf", kind="brochure",
                          summary="Capability statement, no prices. States a minimum order "
                                  "of 10,000 pieces, CONTRADICTING the 5,000 in their own "
                                  "quotation. Section headed 'Our certifications' is empty, "
                                  "behind a questionnaire answer claiming ISO 9001 to 2027."),
               Attachment(filename="shakti_capacity_statement.pdf", kind="capacity",
                          summary="Plant capacity statement, 900 t/month, single unit.")],
    "apex": [Attachment(filename="apex_rate_contract_fy26.pdf", kind="prior_contract",
                        summary="Last year's awarded rate contract - the context needed to "
                                "resolve 'rest same as last year'.")],
}

FREEFORM_TERMS = {
    "shakti": ["Rates ex-works Bhiwandi. GST 18% extra.",
               "Payment 30 days from invoice.",
               "Offer valid 15 days from date of quotation.",
               "Die charges for die-cut items are included in the unit rate."],
    "nova": ["All rates FOR Bhiwandi DC, inclusive of GST.",
             "Payment terms 45 days from GRN.",
             "Offer valid 30 days.",
             "A discount of 3% applies where payment is received within 15 days of invoice."],
    "meridian": ["Rates quoted in USD, ex-works Chennai. GST extra as applicable.",
                 "Rates hold at annual offtake above 50,000 pieces per line; below that "
                 "volume an uplift of 12-15% applies.",
                 "Payment terms 90 days from bill of lading.",
                 "Tooling for die-cut items is charged separately at INR 18,500 per die.",
                 "Offer valid 30 days from date hereof."],
    "ganesh": ["Rates per 100 pieces, ex-works Ambernath. GST extra.",
               "Payment 30 days. Offer valid 21 days."],
    "apex": ["Rs 42/kg for the 5-ply, 38 for the 3-ply, rest same as last year, freight extra."],
}


def build() -> GroundTruth:
    rng = random.Random(SEED)
    lines = build_lines()

    rfx = Rfx(
        rfx_id="RFX-2026-CORR-011",
        title="Annual corrugated packaging requirement, FY27",
        buyer_org="Nandan Consumer Products Ltd",
        category="Corrugated packaging",
        currency="INR",
        issued_date="2026-08-24",
        response_due="2026-09-02",
        award_target="2026-09-24",
        delivery_point="Bhiwandi Distribution Centre, Maharashtra",
        required_incoterm="FOR Bhiwandi DC",
        required_payment_terms="45 days from GRN",
        cost_of_capital_pct=9.0,
        lines=lines,
        questionnaire=QUESTIONNAIRE,
    )

    # Last year's awarded rates - the incumbent quotes deltas against these.
    prior = [
        PriorContractLine(line_no=l.line_no,
                          rate_inr=round(base_price_inr(l) * 0.965, 2),
                          uom=l.uom)
        for l in lines if not l.introduced_this_year
    ]

    submissions: list[VendorSubmission] = []
    for v in VENDORS:
        quotes: list[VendorLineQuote] = []
        for l in lines:
            if l.line_no in NO_QUOTE[v.vendor_id]:
                continue
            jitter = 1.0 + rng.uniform(-0.06, 0.06)
            price = base_price_inr(l) * MARGIN[v.vendor_id] * jitter

            tooling, amortised, note, prior_ref = None, False, None, False

            # --- vendor-specific quoting habits ---------------------------
            if v.vendor_id == "apex":
                # The incumbent's whole quote is four lines of email. Board
                # rates are given by ply; everything else is "same as last
                # year", which is a pointer, not a price.
                currency = "INR"
                if l.ply in (3, 5) and l.style in (
                        BoxStyle.RSC_0201, BoxStyle.DIECUT_0427, BoxStyle.SHEET):
                    basis = QuoteBasis.PER_KG
                    rate = BOARD_RATE_PER_KG[l.ply]
                else:
                    # 7-ply export, pads and partitions fall under "the rest"
                    basis = QuoteBasis.PER_KG if l.uom == Uom.KG else (
                        QuoteBasis.PER_SET if l.uom == Uom.SET else QuoteBasis.PER_PIECE)
                    rate, note, prior_ref = None, "rest same as last year", True
            elif v.vendor_id == "ganesh":
                # The rate card says "ALL RATES ARE PER 100 PIECES" in red at the
                # top, and means it -- including the fitment lines the buyer buys
                # by the set. One basis for the whole document, and it is not the
                # buyer's.
                basis = QuoteBasis.PER_100
                rate = round(price * 100, 0)
                currency = "INR"
            elif v.vendor_id == "meridian":
                basis = QuoteBasis.PER_KG if l.uom == Uom.KG else (
                    QuoteBasis.PER_SET if l.uom == Uom.SET else QuoteBasis.PER_PIECE)
                rate = round(price / v.fx_rate_at_quote, 4)
                currency = "USD"
                if l.requires_tooling:
                    tooling = DIE_COST_INR       # quoted as a separate line
            else:
                basis = {Uom.KG: QuoteBasis.PER_KG, Uom.SET: QuoteBasis.PER_SET,
                         Uom.HUNDRED: QuoteBasis.PER_100}.get(l.uom, QuoteBasis.PER_PIECE)
                rate = round(price * 100, 2) if basis == QuoteBasis.PER_100 else round(price, 2)
                currency = "INR"
                if v.vendor_id == "shakti" and l.requires_tooling:
                    # Shakti buries the die cost in the unit rate. Invisible at
                    # volume, decisive at MOQ - and it silently breaks any split
                    # that reduces their share of these lines.
                    amortised = True
                    rate = round(rate + DIE_COST_INR / l.annual_qty, 2)

            excludes_sub = bool(l.sub_components) and v.vendor_id in ("meridian", "nova")
            quotes.append(VendorLineQuote(
                line_no=l.line_no,
                excludes_sub_component=excludes_sub,
                rate=None if rate is None else round(rate, 4),
                currency=currency, basis=basis,
                refers_to_prior_contract=prior_ref,
                tooling_inr=tooling, tooling_amortised=amortised, note=note))

        answers = [
            QuestionnaireAnswer(q_no=i + 1, answer=a, evidence_file=f, contradicted_by_evidence=c)
            for i, (a, f, c) in enumerate(QUESTIONNAIRE_ANSWERS[v.vendor_id])
        ]
        submissions.append(VendorSubmission(
            vendor=v, line_quotes=quotes, questionnaire=answers,
            attachments=ATTACHMENTS.get(v.vendor_id, []),
            freeform_terms=FREEFORM_TERMS[v.vendor_id]))

    return GroundTruth(rfx=rfx, prior_contract=prior, submissions=submissions,
                       clarifications=build_clarifications(lines, rng))


# ---------------------------------------------------------------------------
# Round two
# ---------------------------------------------------------------------------
# A tender is not a batch job. Five replies arrive, three of them are missing
# something the comparison needs, and what a buyer does is write back. These are
# the second replies — real content, so that the cells they resolve are resolved
# by a vendor rather than by a guess.
#
# What each one does downstream is the point:
#
#   apex      supplies the box weights for six lines quoted per kilogram. Those
#             six cells are the system's seven unresolved ones; five of them
#             become real prices. Without the weight there is no price, and no
#             amount of cleverness makes one.
#   nova      sends a RENEWED ISO certificate. Their first answer said "yes" and
#             the attached certificate had expired in March, which disqualified
#             them. A current certificate puts them back in the running — a
#             follow-up that CHANGES WHO CAN WIN, which is the whole argument for
#             doing a second round at all.
#   ganesh    confirms they are not certified. No miracle: the gap was real, the
#             answer is no, and they stay out. A loop where every follow-up
#             rescues the vendor would be a sales demo.
#   meridian  offers a small-lot rate above their 50,000 minimum, with a
#             surcharge — which is what a real exporter says.
#   shakti    is absent from this list, because they quoted on the buyer's own
#             basis and answered everything. Nothing to ask.

def build_clarifications(lines, rng) -> list:
    from contracts.quote import Clarification
    by_no = {l.line_no: l for l in lines}

    # The six lines Apex priced per kilogram and the buyer has no weight for.
    no_weight = [l.line_no for l in lines
                 if l.unit_weight_g is None and l.uom != Uom.KG
                 and l.line_no not in NO_QUOTE["apex"]]
    apex_weights = {}
    for n in no_weight:
        l = by_no[n]
        # Their production weights, close to but not identical with the
        # buyer's own estimate — which is the point of asking them.
        apex_weights[n] = round(piece_weight_g(l) * (1.0 + rng.uniform(-0.03, 0.05)), 1)

    out = [
        Clarification(
            vendor_id="apex",
            asked_for=[f"finished weight per piece for lines "
                       f"{', '.join(str(n) for n in no_weight)}"],
            received_at="2026-09-05",
            reply_text=(
                "Rakesh here.\n\n"
                "Weights as per our production standard, finished and glued, "
                "average of last three runs:\n\n"
                + "\n".join(f"  Line {n}  {by_no[n].code}  {w:.0f} g"
                             for n, w in apex_weights.items())
                + "\n\nRates per kg as quoted earlier. Freight extra as before.\n\n"
                  "Regards\nRakesh Shetty\nApex Packwell"),
            unit_weights_g=apex_weights),

        Clarification(
            vendor_id="nova",
            asked_for=["a current ISO 9001 certificate — the one attached to "
                       "your reply expired on 31 March 2026"],
            received_at="2026-09-05",
            reply_text=(
                "Dear Sir,\n\n"
                "Apologies — the certificate attached earlier was the previous "
                "cycle. Our recertification completed in April. Current "
                "certificate NC/QMS/2219-R3 is valid to 12 April 2029, copy "
                "attached.\n\n"
                "All other terms stand.\n\n"
                "Regards\nPriya Menon\nNova Corrugators"),
            questionnaire=[QuestionnaireAnswer(
                q_no=1,
                answer=("Yes - ISO 9001:2015, cert. NC/QMS/2219-R3, "
                        "valid to 12 Apr 2029"),
                evidence_file="nova_iso9001_certificate_r3.pdf",
                contradicted_by_evidence=False)],
            attachments=[Attachment(
                filename="nova_iso9001_certificate_r3.pdf", kind="iso9001",
                valid_until="2029-04-12",
                summary="ISO 9001:2015 certificate, recertified April 2026, "
                        "NC/QMS/2219-R3")]),

        Clarification(
            vendor_id="ganesh",
            asked_for=["ISO 9001 certification status",
                       "the test method behind your 22 BF figure"],
            received_at="2026-09-06",
            reply_text=(
                "Sir,\n\n"
                "We are not ISO certified. We have applied, audit is expected "
                "March 2027.\n\n"
                "22 BF is as per IS 2771, tested at Ambernath by our supplier's "
                "lab.\n\n"
                "Ganesh Boxes\n"),
            questionnaire=[
                QuestionnaireAnswer(q_no=1, answer="Not certified - applied, audit expected Mar 2027"),
                QuestionnaireAnswer(q_no=8, answer="22 BF as per IS 2771 (supplier lab, Ambernath)")],
            declined="ISO 9001 certification — not held, and not expected before March 2027"),

        Clarification(
            vendor_id="meridian",
            asked_for=["a rate for the lines below your 50,000-piece minimum"],
            received_at="2026-09-07",
            reply_text=(
                "Dear Team,\n\n"
                "We can supply below our standard 50,000 pc minimum at a "
                "small-lot surcharge. Revised minimum 9,000 pc. Rates as "
                "quoted plus 13.5% on the affected lines, which is our "
                "short-run set-up recovery.\n\n"
                "Best regards\nS. Rajagopal\nMeridian Packaging International"),
            moq_pieces=9000),
    ]
    return out


def main() -> None:
    gt = build()
    out = HERE / "ground_truth.json"
    out.write_text(json.dumps(gt.model_dump(mode="json"), indent=2), encoding="utf-8")

    n_lines = len(gt.rfx.lines)
    print(f"wrote {out}")
    print(f"  {n_lines} buyer lines, {len(gt.submissions)} vendors")
    for s in gt.submissions:
        missing = len(NO_QUOTE[s.vendor.vendor_id])
        print(f"  {s.vendor.name:38s} {len(s.line_quotes):2d}/{n_lines} lines "
              f"({s.vendor.reply_format}, {s.vendor.currency})"
              + (f"  [no-quote: {missing}]" if missing else ""))
    unresolvable = [l.line_no for l in gt.rfx.lines
                    if l.unit_weight_g is None and l.uom != Uom.KG]
    print(f"  lines with no weight on file (block Apex's per-kg quote): {unresolvable}")
    print(f"\n  round two — {len(gt.clarifications)} vendors have something to clarify")
    for c in gt.clarifications:
        what = []
        if c.unit_weights_g:
            what.append(f"{len(c.unit_weights_g)} box weights")
        if c.questionnaire:
            what.append(f"{len(c.questionnaire)} corrected answer(s)")
        if c.moq_pieces:
            what.append(f"minimum order down to {c.moq_pieces:,}")
        if c.declined:
            what.append("declines one ask")
        print(f"    {c.vendor_id:10s} {', '.join(what)}")


if __name__ == "__main__":
    main()
