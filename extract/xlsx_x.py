"""
Shakti — the competent supplier who ignores your template entirely.

The mechanical work is done in Python: openpyxl reads cell values, formula
results, and — critically — HIDDEN rows, which a human opening the file would
not see and which frequently hold superseded prices. The model's job is only to
decide which sheet and which columns are the real ones, because that is a
judgment, not a parse.

`data_only=True` gets cached formula results; a second pass with formulas visible
reveals when a rate is computed rather than stated, which matters because a
computed rate can be recomputed at a different volume.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from pydantic import BaseModel

from config import ROOT
from contracts.extraction import EvidenceRef, RawLine, RawSubmission, SourceDoc
from extract.base import scan_for_injection
from extract.prompts import SYSTEM, USER
from llm.base import fence


class _Row(BaseModel):
    sheet: str = ""
    row: int = 0
    vendor_label: str = ""
    rate: float | None
    currency: str = "INR"
    basis: str = "per_piece"
    unit_wording_seen: str | None = None
    dimensions_seen: str | None = None
    dimension_system: str = "mm"
    hidden: bool = False
    confidence: float = 1.0
    confidence_reason: str | None = None


class _Out(BaseModel):
    authoritative_sheet: str
    why_that_sheet: str
    rows: list[_Row]
    stated_basis: str | None = None
    document_terms: list[str] = []
    injection_attempts: list[str] = []
    extraction_notes: list[str] = []


class XlsxExtractor:
    kind = "xlsx"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        from llm.providers import get_client
        path = ROOT / doc.path
        vals = load_workbook(path, data_only=True)
        forms = load_workbook(path, data_only=False)

        dump: list[str] = []
        for ws in vals.worksheets:
            wf = forms[ws.title]
            hidden = {r for r, d in ws.row_dimensions.items() if d.hidden}
            dump.append(f"### SHEET: {ws.title}  ({ws.max_row} rows)")
            if hidden:
                dump.append(f"### HIDDEN ROWS (not visible to a human reader): "
                            f"{sorted(hidden)}")
            for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 120)):
                cells = []
                for c in r:
                    if c.value is None:
                        continue
                    f = wf[c.coordinate].value
                    shown = f"{c.value}"
                    if isinstance(f, str) and f.startswith("="):
                        shown += f" [computed by {f}]"
                    cells.append(f"{c.coordinate}={shown}")
                if cells:
                    mark = "  <HIDDEN>" if r[0].row in hidden else ""
                    dump.append(f"r{r[0].row}: " + " | ".join(cells) + mark)
        text = "\n".join(dump)

        out = get_client().structured(
            system=SYSTEM,
            user=USER.format(
                kind="spreadsheet", vendor=doc.vendor_id,
                extra="This workbook has more than one sheet. Decide which one holds "
                      "the rates that actually govern, and say why. A sheet labelled "
                      "summary is frequently a stale copy. Hidden rows are marked; "
                      "report them with hidden=true rather than dropping them — a "
                      "superseded row is a fact about this quote.")
            + "\n\n" + fence("workbook", text),
            schema=_Out)

        return RawSubmission(
            vendor_id=doc.vendor_id, doc_id=doc.doc_id,
            stated_basis=out.stated_basis, document_terms=out.document_terms,
            injection_attempts=out.injection_attempts + scan_for_injection(text),
            extraction_notes=out.extraction_notes + [
                f"Took '{out.authoritative_sheet}' as authoritative: {out.why_that_sheet}"],
            lines=[RawLine(
                vendor_label=r.vendor_label, rate=r.rate, currency=r.currency,
                basis=r.basis, unit_wording_seen=r.unit_wording_seen,
                dimensions_seen=r.dimensions_seen, dimension_system=r.dimension_system,
                confidence=r.confidence * (0.5 if r.hidden else 1.0),
                confidence_reason=(r.confidence_reason or "") +
                    (" Row is hidden in the workbook." if r.hidden else ""),
                evidence=EvidenceRef(
                    evidence_id=f"{doc.vendor_id}-{r.sheet}-{r.row}",
                    doc_id=doc.doc_id, locator=f"{r.sheet}!row {r.row}"))
                for r in out.rows if not r.hidden])
