"""
Company profile brochures — the document nobody asked for and everybody sends.

Modelled directly on three real published corrugated-industry brochures (YOJ
Pack, Trident PBI, Pramukh Packaging — see data/SOURCES.md). The pattern across
all three is consistent and it creates failure modes a clean quote never does:

  - 40-70% of the document is marketing narrative
  - the product range advertised is mostly NOT what the buyer asked about
    (Pramukh is a corrugated company whose brochure lists BOPP tape and stretch
    film; YOJ's catalogue is mostly honeycomb board and paper pallets)
  - where prices appear at all they are in units the buyer's line cannot
    consume: Rs 160 per square metre, Rs 850 per pallet, Rs 10 per piece
  - MOQs are buried in prose: "5000-box minimum", "1000/month minimum"
  - capacity is stated twice in incompatible units: boxes/day AND tonnes/year
  - Trident's brochure has a section headed "OUR CERTIFICATIONS" with nothing
    underneath it. Absence of evidence, laid out as though it were presence.

The extraction problem this creates is different in kind from a messy quote. It
is a SIGNAL-TO-NOISE problem: sixty products are described, thirty were asked
about, and most of the overlap is superficial. A system that tries to match
everything will confidently attach a catalogue price to a line it does not
belong to — and unlike a bad parse, that error looks completely reasonable.

The rule the product has to hold: **a catalogue price is not a bid.** Finding
it is useful. Treating it as a quote is not.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from contracts.quote import GroundTruth

S = getSampleStyleSheet()


def _styles(accent: colors.Color):
    return {
        "body": ParagraphStyle("b", parent=S["Normal"], fontName="Helvetica",
                               fontSize=9, leading=13.5),
        "lead": ParagraphStyle("l", parent=S["Normal"], fontName="Helvetica",
                               fontSize=10.5, leading=16, textColor=colors.HexColor("#4A4A4A")),
        "h1": ParagraphStyle("h1", parent=S["Normal"], fontName="Helvetica-Bold",
                             fontSize=22, textColor=accent, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=S["Normal"], fontName="Helvetica-Bold",
                             fontSize=13, textColor=accent, spaceBefore=14, spaceAfter=6),
        "small": ParagraphStyle("s", parent=S["Normal"], fontName="Helvetica",
                                fontSize=7.5, leading=10.5, textColor=colors.HexColor("#7A7A7A")),
        "cell": ParagraphStyle("c", parent=S["Normal"], fontName="Helvetica",
                               fontSize=8, leading=10.5),
    }


def _doc(path: Path, accent: colors.Color, org: str, tag: str):
    def deco(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(accent)
        canvas.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#8A8A8A"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(20 * mm, 12 * mm, f"{org}  ·  {tag}")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))
        canvas.restoreState()

    d = BaseDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=22 * mm, bottomMargin=20 * mm)
    d.addPageTemplates([PageTemplate(
        id="p", frames=[Frame(d.leftMargin, d.bottomMargin, d.width, d.height, id="f")],
        onPage=deco)])
    return d


def _price_table(rows, st, accent):
    data = [[Paragraph(f"<b>{h}</b>", st["cell"]) for h in
             ["Product", "Specification", "Unit", "Indicative rate", "Minimum order"]]]
    for r in rows:
        data.append([Paragraph(c, st["cell"]) for c in r])
    t = Table(data, colWidths=[42 * mm, 48 * mm, 22 * mm, 28 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5D5D5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ---------------------------------------------------------------------------

def render_ganesh(out_dir: Path) -> Path:
    """The small converter's catalogue.

    Two traps, both taken from real brochures:

    1. Most of the range is not what the buyer asked about, and the prices that
       do appear are per square metre or per pallet — units no line item in the
       RFx can consume.
    2. It advertises 7-ply export cartons WITH A PRICE, while the rate card the
       same vendor sent says in black and white "WE DO NOT SUPPLY 7 PLY EXPORT
       CARTONS OR SHEETS." Brochures are printed once and go stale; rate cards
       are current. The system must notice the contradiction and must not treat
       the brochure figure as a bid on lines 16-18.
    """
    accent = colors.HexColor("#E8602B")
    st = _styles(accent)
    out = out_dir / "ganesh_company_profile.pdf"
    doc = _doc(out, accent, "Ganesh Boxes & Cartons", "Company profile 2026")
    s = []

    s += [Paragraph("GANESH BOXES &amp; CARTONS", st["h1"]),
          Paragraph("Packaging solutions since 2009  ·  Ambernath, Maharashtra", st["small"]),
          Spacer(1, 14),
          Paragraph("What started in a rented gala with two manual machines is today a "
                    "trusted name in corrugated packaging across the Mumbai-Pune belt. "
                    "Our commitment to quality, timely delivery and customer satisfaction "
                    "has earned us the confidence of more than 180 regular buyers.", st["lead"]),
          Spacer(1, 10),
          Paragraph("In an industry where packaging is often treated as an afterthought, we "
                    "believe the box is the first thing your customer touches. That belief "
                    "drives everything we do, from raw material selection to final despatch.",
                    st["body"])]

    s += [Paragraph("Plant and machinery", st["h2"])]
    for m in ["Corrugation machine, E and B flute, 42 inch and 52 inch",
              "Flexo 2 colour printer slotter",
              "Semi-automatic stitching machine, 2 nos.",
              "Rotary die punching machine",
              "Quality lab — bursting strength tester, GSM checker, thickness gauge"]:
        s.append(Paragraph(f"&bull;&nbsp; {m}", st["body"]))

    s += [Paragraph("Capacity", st["h2"]),
          # Stated twice, in units that do not convert without a box weight the
          # brochure never gives. Exactly as the real brochures do it.
          Paragraph("<b>28,000+ boxes per day</b> &nbsp;·&nbsp; <b>3,100 metric tonnes "
                    "per annum</b> &nbsp;·&nbsp; Two shifts, extendable to three at short "
                    "notice.", st["body"])]

    s.append(PageBreak())
    s += [Paragraph("Our product range", st["h2"]),
          Paragraph("Indicative rates below are for planning purposes and are subject to "
                    "prevailing kraft paper prices. Please contact our sales team for a "
                    "firm quotation against your specific requirement.", st["small"]),
          Spacer(1, 8)]

    # Most of this range is not what the RFx asked about, and the units are the
    # brochure's own, not the buyer's.
    rows = [
        ["Corrugated boxes, 3 ply", "Single wall, 120-150 GSM, 16 BF",
         "per box", "Rs 8 – 28", "2,000 nos"],
        ["Corrugated boxes, 5 ply", "Double wall, 150-180 GSM, 18-22 BF",
         "per box", "Rs 26 – 82", "2,000 nos"],
        ["<b>Export cartons, 7 ply</b>", "<b>Triple wall, 200 GSM, 24 BF, heavy duty</b>",
         "<b>per box</b>", "<b>Rs 96 – 240</b>", "<b>1,000 nos</b>"],
        ["Die-cut mailers", "E flute, 2 colour flexo, custom die",
         "per box", "Rs 14 – 40", "5,000 nos"],
        ["Honeycomb corner supports", "20-50 mm, for glass and appliances",
         "per piece", "Rs 10", "2,000 nos"],
        ["Honeycomb board", "20-60 mm thickness, fitments and partitions",
         "per sq. metre", "Rs 160", "500 sq. m"],
        ["Paper pallets", "Four-way entry, 800-1200 kg capacity",
         "per pallet", "Rs 850", "100 nos"],
        ["Office waste bins", "Corrugated, 30-70 litre",
         "per piece", "Rs 55 – 140", "500 nos"],
        ["BOPP self-adhesive tape", "Transparent and brown, 40-72 micron",
         "per roll", "Rs 32 – 78", "144 rolls"],
        ["Stretch film", "Manual and machine grade, 17-23 micron",
         "per kg", "Rs 148", "50 kg"],
    ]
    s.append(_price_table(rows, st, accent))
    s += [Spacer(1, 8),
          Paragraph("Minimum order for printed and custom sizes is 5,000 boxes. Standard "
                    "sizes can be supplied against a minimum of 2,000 boxes. Lead time is "
                    "normally 10 to 14 days from confirmation of artwork.", st["body"])]

    s.append(PageBreak())
    # The section that promises evidence and delivers none — verbatim structure
    # from a real brochure.
    s += [Paragraph("Our certifications", st["h2"]), Spacer(1, 40),
          Paragraph("Our valued customers", st["h2"]),
          Paragraph("Balaji Foods &bull; Kohinoor Appliances &bull; Sharda Motors &bull; "
                    "Ganga Pharma &bull; Vishwas Electricals &bull; Deccan Beverages &bull; "
                    "Mahalaxmi Textiles &bull; Sunrise Ceramics &bull; JBF Polymers &bull; "
                    "Emerald Chemicals &bull; Konkan Marine Exports &bull; Prime Auto Parts",
                    st["body"]),
          Spacer(1, 16),
          Paragraph("Contact", st["h2"]),
          Paragraph("Gala 12, Morivali MIDC, Ambernath (W), Thane 421505<br/>"
                    "Ph 0251-2601188 &nbsp;·&nbsp; sales@ganeshboxes.in<br/>"
                    "GSTIN 27ADQPG4482N1ZS &nbsp;·&nbsp; Udyam-MH-19-0044821", st["body"])]

    doc.build(s)
    return out


def render_shakti(out_dir: Path) -> Path:
    """The mid-size converter's capability profile.

    No prices at all — which makes it useless as a quote and useful as evidence.
    Two things it does carry:

    1. A minimum order stated in marketing prose (10,000 pieces) that CONTRADICTS
       the 5,000 in their actual quotation. Two numbers, two documents, same
       vendor, and the quote is the one that governs.
    2. An empty certifications section, sitting behind a questionnaire answer
       that claims ISO 9001 valid to June 2027. Not a contradiction — but not
       the corroboration a buyer would assume either.
    """
    accent = colors.HexColor("#1F3864")
    st = _styles(accent)
    out = out_dir / "shakti_company_profile.pdf"
    doc = _doc(out, accent, "Shakti Packaging Pvt Ltd", "Capability statement")
    s = []

    s += [Paragraph("SHAKTI PACKAGING PRIVATE LIMITED", st["h1"]),
          Paragraph("Established 1996  ·  Bhiwandi, Maharashtra", st["small"]),
          Spacer(1, 14),
          Paragraph("Three decades of converting excellence. From a single semi-automatic "
                    "corrugator to a 50,000 square foot integrated facility, Shakti has "
                    "grown alongside the customers we serve — and we have never lost sight "
                    "of the fact that packaging is a promise kept between a brand and the "
                    "person who opens the carton.", st["lead"]),
          Spacer(1, 10),
          Paragraph("Turnover in excess of Rs 68 crore. Over 240 employees. A single "
                    "location, run properly.", st["body"])]

    s += [Paragraph("Manufacturing", st["h2"])]
    for m in ["5 ply automatic corrugator, 72 inch",
              "Flexo 4 colour printer slotter die cutter",
              "Flexo 2 colour printer slotter die cutter",
              "Folder gluer",
              "Semi-automatic stitching machines, 4 nos.",
              "Raw material storage, 13,000 sq ft; finished goods storage, 9,000 sq ft"]:
        s.append(Paragraph(f"&bull;&nbsp; {m}", st["body"]))

    s += [Paragraph("Quality laboratory", st["h2"]),
          Paragraph("Thickness checker &bull; GSM checker &bull; bursting strength tester "
                    "&bull; edge crush and ring crush tester &bull; moisture meter &bull; "
                    "calibrated platform scales", st["body"])]

    s += [Paragraph("Capacity and terms", st["h2"]),
          Paragraph("<b>90,000+ boxes per day</b> across two shifts. <b>18,000 metric "
                    "tonnes per year</b> of board conversion.", st["body"]),
          Spacer(1, 4),
          # 10,000 here; 5,000 in the actual quotation. Both are stated as fact.
          Paragraph("We accept orders against a minimum quantity of 10,000 pieces per "
                    "item per despatch, and our standard lead time is three weeks from "
                    "receipt of a firm order and approved artwork.", st["body"])]

    s.append(PageBreak())
    s += [Paragraph("Our certifications", st["h2"]), Spacer(1, 44),
          Paragraph("Industries served", st["h2"]),
          Paragraph("Fast moving consumer goods &bull; pharmaceuticals &bull; automotive "
                    "components &bull; home appliances &bull; agrochemicals &bull; "
                    "engineering exports", st["body"]),
          Spacer(1, 14),
          Paragraph("A selection of our customers", st["h2"]),
          Paragraph("Godrej Consumer &bull; Bosch Rexroth &bull; Ford India &bull; "
                    "Manpasand Beverages &bull; JBF Industries &bull; Balaji Wafers &bull; "
                    "Emerson Process India &bull; Kansai Nerolac &bull; Finolex &bull; "
                    "Supreme Industries &bull; Havells &bull; Blue Star &bull; Crompton "
                    "&bull; Pidilite &bull; Asian Paints", st["body"]),
          Spacer(1, 16),
          Paragraph("Plot 44, MIDC Bhiwandi, Thane 421302 &nbsp;·&nbsp; "
                    "GSTIN 27AAFCS4471K1ZP", st["small"])]

    doc.build(s)
    return out


def render_all(gt: GroundTruth, out_dir: Path) -> list[Path]:
    return [render_ganesh(out_dir), render_shakti(out_dir)]
