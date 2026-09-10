"""
Nova — the clean PDF that hides its discount in a page-3 footnote.

Two passes, because the text layer and the page image fail differently. The text
layer is exact where it exists and silently drops table structure; the rendered
page keeps the layout a human reads by. Footnotes are the case that punishes
using only one: a 3% discount in six-point grey at the foot of the last page is
present in the text layer, trivially, and invisible to anyone skimming the table.
"""

from __future__ import annotations

from pydantic import BaseModel

from config import ROOT
from contracts.extraction import EvidenceRef, RawLine, RawSubmission, SourceDoc
from extract.base import scan_for_injection
from extract.prompts import SYSTEM, USER
from llm.base import fence


class _Row(BaseModel):
    page: int
    vendor_label: str
    rate: float | None
    currency: str = "INR"
    basis: str
    unit_wording_seen: str | None = None
    dimension_system: str = "mm"
    confidence: float = 1.0
    confidence_reason: str | None = None


class _Out(BaseModel):
    rows: list[_Row]
    stated_basis: str | None = None
    document_terms: list[str] = []
    # Called out separately because this is precisely what gets missed, and a
    # schema field is a better reminder than a sentence in a prompt.
    footnotes_and_conditions: list[str] = []
    lines_absent_from_schedule: str | None = None
    injection_attempts: list[str] = []
    extraction_notes: list[str] = []


class PdfExtractor:
    kind = "pdf"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        from pypdf import PdfReader
        from llm.providers import get_client

        path = ROOT / doc.path
        reader = PdfReader(str(path))
        pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        text = "\n\n".join(f"### PAGE {n}\n{t}" for n, t in pages)

        images: list[bytes] = []
        try:                       # layout matters; render if poppler is present
            from pdf2image import convert_from_path
            import io
            for img in convert_from_path(str(path), dpi=130):
                buf = io.BytesIO(); img.convert("RGB").save(buf, "JPEG", quality=82)
                images.append(buf.getvalue())
        except Exception:          # noqa: BLE001 - text layer alone is enough
            pass

        out = get_client().structured(
            system=SYSTEM,
            user=USER.format(
                kind="PDF", vendor=doc.vendor_id,
                extra="Read EVERY page, including the last. Discounts, rebates, "
                      "validity periods and substitution clauses are routinely stated "
                      "once, in small type, after the rate table — and they change the "
                      "price. Put every one you find in footnotes_and_conditions. If "
                      "the vendor omitted items rather than marking them no-quote, say "
                      "so in lines_absent_from_schedule.")
            + "\n\n" + fence("pdf_text", text),
            schema=_Out, images=images[:6])

        notes = out.extraction_notes + [f"footnote/condition: {f}"
                                        for f in out.footnotes_and_conditions]
        if out.lines_absent_from_schedule:
            notes.append(out.lines_absent_from_schedule)

        return RawSubmission(
            vendor_id=doc.vendor_id, doc_id=doc.doc_id,
            stated_basis=out.stated_basis,
            document_terms=out.document_terms + out.footnotes_and_conditions,
            injection_attempts=out.injection_attempts + scan_for_injection(text),
            extraction_notes=notes,
            lines=[RawLine(
                vendor_label=r.vendor_label, rate=r.rate, currency=r.currency,
                basis=r.basis, unit_wording_seen=r.unit_wording_seen,
                dimension_system=r.dimension_system, confidence=r.confidence,
                confidence_reason=r.confidence_reason,
                evidence=EvidenceRef(
                    evidence_id=f"{doc.vendor_id}-p{r.page}-{abs(hash(r.vendor_label)) % 9999}",
                    doc_id=doc.doc_id, locator=f"p{r.page}", page=r.page))
                for r in out.rows])
