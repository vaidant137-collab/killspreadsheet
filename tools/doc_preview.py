"""
Render a source document inside the drawer, rather than handing over a download.

A buyer checking a number should not have to leave the screen, find the file in
their Downloads folder, open Excel, work out which sheet, and then come back and
remember what they were checking. That round trip is the reason provenance goes
unchecked in practice — not that the evidence is missing, but that looking at it
costs more than trusting the number.

So every source kind renders in place:

    xlsx   the grid, with the cited cell marked and the sheet it lives on named
    eml    headers and body, as mail
    docx   paragraphs and tables, in order
    pdf    the page, in an iframe          (already worked)
    jpg    the photograph, with the crop   (already worked)

The two that matter most are the ones that used to be links. Shakti's real rates
are on the SECOND sheet and three rows are hidden; Apex's whole quotation is four
lines of email. Both are unreadable as a download and obvious as a preview.
"""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

MAX_ROWS = 80
MAX_COLS = 14


def preview(path: Path, locator: str = "") -> dict:
    """Structured content for the drawer. Never raises for a readable file —
    a preview that 500s is worse than the download it replaced."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".xlsx", ".xlsm"):
            return _xlsx(path, locator)
        if suffix == ".eml":
            return _eml(path)
        if suffix == ".docx":
            return _docx(path, locator)
    except Exception as e:                                   # noqa: BLE001
        return {"kind": "error", "message": f"{type(e).__name__}: {e}"}
    return {"kind": "other"}


# ---------------------------------------------------------------------------

def _xlsx(path: Path, locator: str) -> dict:
    import openpyxl

    # locator looks like "Rate Working!L14" — sheet name, then the cell.
    want_sheet, want_cell = None, None
    m = re.match(r"(?:'?(?P<sheet>[^'!]+)'?!)?(?P<cell>[A-Z]{1,3}\d+)$", locator.strip())
    if m:
        want_sheet, want_cell = m.group("sheet"), m.group("cell")

    # data_only=False keeps formulas visible. Shakti's real rate IS a formula,
    # and showing the computed value would hide exactly the thing worth seeing.
    wb = openpyxl.load_workbook(path, data_only=False)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, MAX_ROWS),
                              max_col=min(ws.max_column, MAX_COLS)):
            rows.append([{"ref": c.coordinate,
                          "v": "" if c.value is None else str(c.value),
                          "hidden": bool(ws.row_dimensions[c.row].hidden)}
                         for c in r])
        sheets.append({
            "name": ws.title, "rows": rows,
            "truncated": ws.max_row > MAX_ROWS or ws.max_column > MAX_COLS,
            # Hidden rows are a trap in this dataset, not a rendering detail:
            # superseded lines get hidden rather than deleted. Say how many.
            "hidden_rows": sorted(n for n, d in ws.row_dimensions.items() if d.hidden),
        })
    return {"kind": "sheet", "sheets": sheets,
            "focus_sheet": want_sheet or (sheets[0]["name"] if sheets else None),
            "focus_cell": want_cell}


def _eml(path: Path) -> dict:
    msg = BytesParser(policy=policy.default).parse(path.open("rb"))
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body is not None and body.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", "", text)
    return {"kind": "mail",
            "headers": [[k, str(v)] for k, v in msg.items()
                        if k.lower() in ("from", "to", "cc", "subject", "date")],
            "body": text.strip(),
            "attachments": [p.get_filename() for p in msg.iter_attachments()
                            if p.get_filename()]}


def _docx(path: Path, locator: str) -> dict:
    import docx

    d = docx.Document(str(path))
    parts = []
    for p in d.paragraphs:
        t = p.text.strip()
        if t:
            parts.append({"type": "h" if p.style.name.startswith("Heading") else "p",
                          "text": t})
    tables = []
    for t in d.tables:
        tables.append([[c.text.strip() for c in row.cells] for row in t.rows[:MAX_ROWS]])
    m = re.search(r"table row (\d+)", locator or "")
    return {"kind": "prose", "paragraphs": parts, "tables": tables,
            "focus_row": int(m.group(1)) if m else None}
