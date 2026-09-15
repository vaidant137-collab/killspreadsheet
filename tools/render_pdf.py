"""
Nova Corrugators — the clean, professional PDF that hides its discount.

Traps rendered here:
  - a 3% early-payment discount stated ONLY in a footnote on the last page
  - the rate table breaks across pages with the header repeated
  - three lines simply absent (no die-cutting capability) rather than marked no-quote
  - rates are FOR destination and GST-inclusive, so they look higher than they are

Also renders the attachments, including the ISO 9001 certificate whose expiry
date contradicts Nova's own "Yes" on the questionnaire.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

from contracts.quote import GroundTruth
from tools.labels import nova as label

NAVY = colors.HexColor("#123A5E")
GREY = colors.HexColor("#6B7076")
RULE = colors.HexColor("#C9CDD2")

S = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=S["Normal"], fontName="Helvetica", fontSize=8.5, leading=12)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.2, leading=10, textColor=GREY)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.6, leading=9.6)
H1 = ParagraphStyle("h1", parent=S["Normal"], fontName="Helvetica-Bold", fontSize=15,
                    textColor=NAVY, spaceAfter=2)
H2 = ParagraphStyle("h2", parent=S["Normal"], fontName="Helvetica-Bold", fontSize=9.5,
                    textColor=NAVY, spaceBefore=10, spaceAfter=4)


def _letterhead(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 26 * mm, A4[0], 26 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(20 * mm, A4[1] - 15 * mm, "NOVA CORRUGATORS PVT LTD")
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(20 * mm, A4[1] - 20.5 * mm,
                      "Survey 118/2, Sativali Road, Vasai East, Palghar 401208  ·  "
                      "GSTIN 27AACCN2219R1Z4  ·  ISO 9001:2015  ·  FSC C148820")
    canvas.setFillColor(GREY)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
    canvas.drawString(20 * mm, 12 * mm, "Quotation NCPL/2026-27/Q-0912  ·  Confidential")
    canvas.setStrokeColor(RULE)
    canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
    canvas.restoreState()


def _doc(path: Path) -> BaseDocTemplate:
    doc = BaseDocTemplate(str(path), pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=32 * mm, bottomMargin=20 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="lh", frames=[frame], onPage=_letterhead)])
    return doc


def render(gt: GroundTruth, out_dir: Path) -> Path:
    sub = next(s for s in gt.submissions if s.vendor.vendor_id == "nova")
    lines = {l.line_no: l for l in gt.rfx.lines}
    out = out_dir / "nova_quotation_NCPL-2026-27-Q-0912.pdf"
    doc = _doc(out)
    story = []

    story.append(Paragraph("Quotation for annual corrugated packaging, FY27", H1))
    story.append(Paragraph(
        "To: Nandan Consumer Products Ltd, Bhiwandi Distribution Centre &nbsp;·&nbsp; "
        "Kind attn: Category Purchase &nbsp;·&nbsp; Ref your enquiry "
        f"{gt.rfx.rfx_id} dated 24 August 2026", SMALL))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "We thank you for the opportunity. Our rates for the referenced requirement are "
        "set out overleaf. All rates are quoted <b>FOR your Bhiwandi Distribution Centre "
        "and are inclusive of GST</b>. Payment terms 45 days from GRN. This offer is "
        "valid for 30 days.", BODY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Please note we are presently unable to offer against your die-cut mailer "
        "requirement, as we do not operate a die-cutting line. Those items are "
        "therefore not included below.", BODY))

    # Preamble sized so the rate table starts low on page one and runs onto
    # page two. A table that breaks mid-way with its header repeated is a real
    # extraction trap and a common one; a table that happens to fit on one page
    # tests nothing.
    story.append(Paragraph("Basis of quotation", H2))
    for txt in [
        "Rates are computed on 180 GSM virgin kraft liner with semi-chemical fluting "
        "medium, BC flute for five-ply construction and B flute for three-ply, unless "
        "otherwise agreed in writing.",
        "All dimensions stated are internal dimensions in millimetres, in the order "
        "length by width by height, measured in accordance with your enquiry.",
        "Board strength is certified by Edge Crush Test determined per ISO 3037. We do "
        "not quote bursting factor, as the two measures are not interchangeable and we "
        "prefer not to state a figure we have not ourselves measured.",
        "Rates assume despatch in full truck loads to your Bhiwandi Distribution Centre "
        "on a monthly indent, and include palletisation, stretch wrap and freight.",
        "Where an item is not listed in the schedule below, we are not in a position to "
        "offer against it at this time.",
    ]:
        story.append(Paragraph(txt, BODY))
        story.append(Spacer(1, 4))

    story.append(Paragraph("Schedule of rates", H2))
    head = ["Sl.", "Description", "UOM", "Annual qty", "Rate (INR)"]
    rows = [[Paragraph(f"<b>{h}</b>", CELL) for h in head]]
    for i, q in enumerate(sub.line_quotes, start=1):
        l = lines[q.line_no]
        uom = {"piece": "No.", "kg": "Kg", "set": "Set", "100_pieces": "100 Nos."}[l.uom.value]
        rows.append([Paragraph(str(i), CELL), Paragraph(label(l), CELL),
                     Paragraph(uom, CELL),
                     Paragraph(f"{l.annual_qty:,}", CELL),
                     Paragraph(f"{q.rate:,.2f}", CELL)])
    t = Table(rows, colWidths=[10 * mm, 88 * mm, 16 * mm, 24 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # --- page 3: terms. The discount lives here and nowhere else. -----------
    story.append(PageBreak())
    story.append(Paragraph("Commercial terms and conditions", H2))
    for n, txt in enumerate([
        "Rates are firm FOR Nandan Consumer Products Ltd, Bhiwandi Distribution Centre, "
        "and are inclusive of Goods and Services Tax at the prevailing rate.",
        "Payment terms are 45 (forty five) days from Goods Receipt Note.",
        "Minimum order quantity is 3,000 pieces per line item per despatch.",
        "Standard production lead time is 18 days from receipt of firm purchase order.",
        "Board strength is certified to ECT 32 kN/m determined in accordance with ISO 3037. "
        "Certificates of analysis will accompany each despatch.",
        "This offer is valid for 30 (thirty) days from the date hereof, after which rates "
        "are subject to revision in line with movements in kraft paper prices.",
        "Any change to board grade, flute profile, adhesive or manufacturing location will "
        "be notified to the buyer not less than 30 days in advance.",
    ], start=1):
        story.append(Paragraph(f"{n}. &nbsp;{txt}", BODY))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 14))
    story.append(Paragraph("For Nova Corrugators Pvt Ltd", BODY))
    story.append(Spacer(1, 16))
    story.append(Paragraph("S. Ramanathan &nbsp;·&nbsp; Head, Key Accounts", SMALL))

    story.append(Spacer(1, 20))
    rule = Table([[""]], colWidths=[doc.width])
    rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, RULE)]))
    story.append(rule)
    story.append(Spacer(1, 4))
    # THE TRAP. A 3% discount, stated once, in six-point grey, at the foot of
    # the last page. Miss it and Nova loses the award it should have won.
    story.append(Paragraph(
        "*&nbsp;A discount of 3% on invoice value is applicable where payment is "
        "received within 15 days of invoice date. This discount is in addition to the "
        "rates quoted above and is not reflected in the schedule.", SMALL))
    story.append(Paragraph(
        "**&nbsp;Rates quoted are based on 180 GSM virgin kraft liner. Substitution to "
        "test liner, where agreed, attracts a reduction of INR 1.10 per kg of board.", SMALL))

    doc.build(story)
    return out


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def render_nova_iso_certificate(out_dir: Path) -> Path:
    """The document that contradicts the questionnaire. Nova answered 'Yes -
    ISO 9001:2015 certified'. The certificate they attached expired in March.
    Nobody lied; the renewal is late at the plant. This is the most common
    compliance failure in vendor onboarding and it is only ever caught by
    reading the attachment."""
    out = out_dir / "nova_iso9001_certificate.pdf"
    from reportlab.pdfgen import canvas as rl_canvas

    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4
    c.setStrokeColor(NAVY); c.setLineWidth(3)
    c.rect(14 * mm, 14 * mm, w - 28 * mm, h - 28 * mm)
    c.setLineWidth(0.6)
    c.rect(18 * mm, 18 * mm, w - 36 * mm, h - 36 * mm)

    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, h - 45 * mm, "CERTIFICATE OF REGISTRATION")
    c.setFont("Helvetica", 10); c.setFillColor(GREY)
    c.drawCentredString(w / 2, h - 54 * mm, "Quality Management System")
    c.setFont("Helvetica-Bold", 13); c.setFillColor(colors.black)
    c.drawCentredString(w / 2, h - 66 * mm, "ISO 9001:2015")

    c.setFont("Helvetica", 9.5); c.setFillColor(GREY)
    c.drawCentredString(w / 2, h - 82 * mm, "This is to certify that the management system of")
    c.setFont("Helvetica-Bold", 14); c.setFillColor(colors.black)
    c.drawCentredString(w / 2, h - 92 * mm, "NOVA CORRUGATORS PRIVATE LIMITED")
    c.setFont("Helvetica", 8.5); c.setFillColor(GREY)
    c.drawCentredString(w / 2, h - 99 * mm,
                        "Survey 118/2, Sativali Road, Vasai East, Palghar 401208, India")
    c.setFont("Helvetica", 9); c.setFillColor(colors.black)
    c.drawCentredString(w / 2, h - 112 * mm,
                        "has been assessed and found to comply with the requirements of")
    c.drawCentredString(w / 2, h - 119 * mm,
                        "ISO 9001:2015 for the following scope of activities:")
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(w / 2, h - 129 * mm,
                        "Manufacture and supply of corrugated fibreboard boxes, sheets and fitments.")

    y = h - 150 * mm
    for k, v in [("Certificate number", "NC/QMS/2219"),
                 ("Original approval", "12 April 2017"),
                 ("Current issue", "01 April 2023"),
                 ("Expiry date", "31 March 2026")]:
        c.setFont("Helvetica", 9); c.setFillColor(GREY)
        c.drawString(45 * mm, y, k)
        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColor(colors.HexColor("#9E2C2C") if k == "Expiry date" else colors.black)
        c.drawString(105 * mm, y, v)
        y -= 8 * mm

    c.setFont("Helvetica", 7.5); c.setFillColor(GREY)
    c.drawCentredString(w / 2, 42 * mm,
                        "The validity of this certificate is subject to satisfactory surveillance audits.")
    c.drawCentredString(w / 2, 36 * mm,
                        "Issued by Meridian Certification Services (India) Pvt Ltd, accreditation NABCB QM-118.")
    c.save()
    return out


def render_apex_prior_contract(gt: GroundTruth, out_dir: Path) -> Path:
    """Last year's awarded rate contract. Without this document, 'rest same as
    last year' cannot be resolved at all — which is the point."""
    out = out_dir / "apex_rate_contract_fy26.pdf"
    doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=20 * mm, bottomMargin=18 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame])])
    lines = {l.line_no: l for l in gt.rfx.lines}

    story = [
        Paragraph("RATE CONTRACT — FY26", H1),
        Paragraph("Nandan Consumer Products Ltd &nbsp;&larr;&rarr;&nbsp; Apex Packwell, "
                  "Bhiwandi &nbsp;·&nbsp; Contract NCP/RC/FY26/007 &nbsp;·&nbsp; "
                  "Effective 01 April 2025 to 31 March 2026", SMALL),
        Spacer(1, 10),
        Paragraph("Rates below are ex-works Bhiwandi, exclusive of GST, payment 45 days "
                  "from GRN. Freight to buyer's account.", BODY),
        Spacer(1, 8),
    ]
    head = ["Sl.", "Item description", "UOM", "Rate (INR)"]
    rows = [[Paragraph(f"<b>{h}</b>", CELL) for h in head]]
    for i, p in enumerate(gt.prior_contract, start=1):
        l = lines[p.line_no]
        uom = {"piece": "No.", "kg": "Kg", "set": "Set", "100_pieces": "100 Nos."}[l.uom.value]
        rows.append([Paragraph(str(i), CELL),
                     Paragraph(l.description, CELL),
                     Paragraph(uom, CELL),
                     Paragraph(f"{p.rate_inr:,.2f}", CELL)])
    t = Table(rows, colWidths=[10 * mm, 112 * mm, 18 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3A3A3A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    doc.build(story)
    return out


def render_simple_attachment(out_dir: Path, filename: str, title: str,
                             org: str, body: list[str]) -> Path:
    out = out_dir / filename
    doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=24 * mm, bottomMargin=20 * mm)
    doc.addPageTemplates([PageTemplate(
        id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")])])
    story = [Paragraph(title, H1), Paragraph(org, SMALL), Spacer(1, 12)]
    for b in body:
        story.append(Paragraph(b, BODY))
        story.append(Spacer(1, 6))
    doc.build(story)
    return out
