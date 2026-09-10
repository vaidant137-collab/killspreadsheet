"""
Shakti Packaging — the competent supplier who ignores your template entirely.

Traps rendered here:
  - two sheets; the summary sheet carries STALE rates, the second sheet has the real ones
  - three hidden rows
  - the real rate is a FORMULA (base + die amortisation), not a literal
  - own column order, own line naming, dimensions in a single text column
  - die cost silently amortised into the unit rate on the die-cut lines
  - 15-day validity buried in a header cell
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from contracts.quote import GroundTruth
from tools.labels import shakti as label

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=9)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def render(gt: GroundTruth, out_dir: Path) -> Path:
    sub = next(s for s in gt.submissions if s.vendor.vendor_id == "shakti")
    lines = {l.line_no: l for l in gt.rfx.lines}
    wb = Workbook()

    # ------------------------------------------------------------------ sheet 1
    # The summary. Looks like the answer. Is out of date by one revision.
    s1 = wb.active
    s1.title = "Quotation Summary"
    s1["A1"] = "SHAKTI PACKAGING PVT LTD"
    s1["A1"].font = Font(bold=True, size=14, color="1F3864")
    s1["A2"] = "Plot 44, MIDC Bhiwandi, Thane 421302  |  GSTIN 27AAFCS4471K1ZP"
    s1["A2"].font = Font(size=8, color="595959")
    s1["A4"] = "Quotation ref"; s1["B4"] = "SPPL/QT/2026-27/0318"
    s1["A5"] = "Against enquiry"; s1["B5"] = gt.rfx.rfx_id
    s1["A6"] = "Date"; s1["B6"] = "01-Sep-2026"
    s1["A7"] = "Validity"; s1["B7"] = "15 days from date of quotation"
    s1["A8"] = "Terms"; s1["B8"] = "Ex-works Bhiwandi. GST 18% extra. Payment 30 days."
    s1["A9"] = "Note"; s1["B9"] = "Die charges for die-cut items are included in the unit rate."
    for r in range(4, 10):
        s1[f"A{r}"].font = Font(bold=True, size=9)
        s1[f"B{r}"].font = Font(size=9)
    s1.column_dimensions["A"].width = 16
    s1.column_dimensions["B"].width = 62

    s1["A11"] = "SUMMARY OF RATES (indicative - refer 'Rate Working' sheet for final rates)"
    s1["A11"].font = Font(bold=True, size=9, color="C00000")
    hdr = ["Sr", "Item", "Qty p.a.", "Rate"]
    for c, h in enumerate(hdr, start=1):
        cell = s1.cell(row=12, column=c, value=h)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
    for i, q in enumerate(sub.line_quotes, start=1):
        l = lines[q.line_no]
        stale = round((q.rate or 0) * 0.97, 2)     # previous revision, 3% lower
        for c, v in enumerate([i, label(l), l.annual_qty, stale], start=1):
            cell = s1.cell(row=12 + i, column=c, value=v)
            cell.border = BORDER
            cell.font = Font(size=9)
            if c == 4:
                cell.number_format = "0.00"
    s1.column_dimensions["C"].width = 12
    s1.column_dimensions["D"].width = 12

    # ------------------------------------------------------------------ sheet 2
    # The real rates. Column order is Shakti's, not the buyer's.
    s2 = wb.create_sheet("Rate Working")
    headers = ["Sr No", "Description", "Size (mm)", "Ply", "GSM", "BF",
               "UOM", "Annual Qty", "Board Cost", "Conv + Print", "Die Amort",
               "Net Rate", "Remarks"]
    for c, h in enumerate(headers, start=1):
        cell = s2.cell(row=1, column=c, value=h)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    row = 2
    hidden_rows: list[int] = []
    for i, q in enumerate(sub.line_quotes, start=1):
        l = lines[q.line_no]
        die_amort = 0.0
        if q.tooling_amortised:
            die_amort = round(18500.0 / l.annual_qty, 4)
        conv = round((q.rate or 0) * 0.22, 4)
        board = round((q.rate or 0) - conv - die_amort, 4)
        uom = {"piece": "Nos", "kg": "Kgs", "set": "Set", "100_pieces": "Per 100 Nos"}[l.uom.value]
        vals = [i, label(l), _size(l), l.ply, l.liner_gsm, l.bursting_factor,
                uom, l.annual_qty, board, conv, die_amort or None, None,
                "Die cost included in rate" if q.tooling_amortised else None]
        for c, v in enumerate(vals, start=1):
            cell = s2.cell(row=row, column=c, value=v)
            cell.border = BORDER
            cell.font = Font(size=9)
            if c in (9, 10, 11, 12):
                cell.number_format = "0.0000"
        # The real rate is a formula, not a literal. A naive reader that grabs
        # cached values will still work; one that reads the .xlsx XML sees "=I2+J2+K2".
        s2.cell(row=row, column=12).value = f"=I{row}+J{row}+ROUND(K{row},4)"
        s2.cell(row=row, column=12).font = Font(size=9, bold=True)
        s2.cell(row=row, column=12).number_format = "0.00"

        # Three superseded rows, hidden rather than deleted. Classic.
        if i in (7, 18, 24):
            hidden_rows.append(row)
        row += 1

    for r in hidden_rows:
        s2.row_dimensions[r].hidden = True

    widths = [7, 34, 20, 6, 7, 6, 12, 12, 12, 13, 11, 12, 28]
    for c, w in enumerate(widths, start=1):
        s2.column_dimensions[get_column_letter(c)].width = w
    s2.freeze_panes = "A2"

    out = out_dir / "shakti_quotation_SPPL-QT-2026-27-0318.xlsx"
    wb.save(out)
    return out


def _size(l) -> str:
    d = l.dims
    if d.height_mm is None:
        return f"{d.length_mm} x {d.width_mm}"
    return f"{d.length_mm} x {d.width_mm} x {d.height_mm}"
