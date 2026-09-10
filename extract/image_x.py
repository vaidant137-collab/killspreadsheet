"""
Ganesh — a printed rate card, photographed at an angle on a phone.

This is the path the brief singles out, and it is the one where per-row
confidence earns its keep. A shadow across four rows, a rate struck through in
pen with a revision beside it, Indian digit grouping, perspective distortion —
each degrades some rows and not others, and a document-level confidence score
would average all of that into a number that describes nothing.

Two crops of the same image are sent alongside the whole page, because a model
reading a 22-row table at full-page scale loses the digits it needs most.
"""

from __future__ import annotations

import io

from pydantic import BaseModel

from config import ROOT
from contracts.extraction import EvidenceRef, RawLine, RawSubmission, SourceDoc
from extract.prompts import SYSTEM, USER


class _Row(BaseModel):
    row_index: int
    vendor_label: str
    rate: float | None
    currency: str = "INR"
    basis: str
    dimensions_seen: str | None = None
    dimension_system: str = "mm"
    # A printed rate struck through in pen is superseded, not wrong. Both
    # numbers are evidence and the buyer should see which is which.
    printed_rate_struck_through: float | None = None
    handwritten_revision: bool = False
    obscured: bool = False
    confidence: float = 1.0
    confidence_reason: str | None = None


class _Out(BaseModel):
    rows: list[_Row]
    stated_basis: str | None = None
    document_terms: list[str] = []
    legibility_notes: list[str] = []
    injection_attempts: list[str] = []
    extraction_notes: list[str] = []


def _crops(path) -> list[bytes]:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    out = []
    for box in ((0, 0, w, int(h * 0.58)), (0, int(h * 0.42), w, h)):
        c = im.crop(box)
        c = c.resize((min(1600, c.width * 2), int(c.height * min(1600, c.width * 2) / c.width)))
        buf = io.BytesIO(); c.save(buf, "JPEG", quality=92); out.append(buf.getvalue())
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return [buf.getvalue()] + out


class ImageExtractor:
    kind = "image"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        from llm.providers import get_client
        path = ROOT / doc.path

        out = get_client().structured(
            system=SYSTEM,
            user=USER.format(
                kind="photographed rate card", vendor=doc.vendor_id,
                extra="Three images: the whole page, then the top and bottom halves "
                      "enlarged. Use the enlargements for the digits.\n\n"
                      "Work row by row and give EACH row its own confidence.\n"
                      "- Some rows fall under a shadow. Say so, lower the confidence, "
                      "and give your best reading rather than nothing — a flagged "
                      "reading a human can check beats a silent gap.\n"
                      "- Where a printed rate is struck through and a figure is written "
                      "beside it in pen, the handwritten one governs. Record BOTH: put "
                      "the pen figure in `rate` and the printed one in "
                      "`printed_rate_struck_through`.\n"
                      "- Indian digit grouping: 1,20,000 is 120000 and 70,36,800 is "
                      "7036800. Read the grouping, not the character count.\n"
                      "- Dimensions on a card like this are usually INCHES. Record what "
                      "is printed and set dimension_system. Do not convert.\n"
                      "- The header states one basis for every rate on the card. Put it "
                      "in stated_basis and apply it to every row."),
            schema=_Out, images=_crops(path))

        lines = []
        for r in out.rows:
            conf = r.confidence
            reason = r.confidence_reason
            if r.obscured:
                conf = min(conf, 0.62)
                reason = (reason or "") + " Row is obscured in the photograph."
            if r.handwritten_revision:
                conf = min(conf, 0.75)
                reason = ((reason or "") +
                          f" Printed rate {r.printed_rate_struck_through} struck through; "
                          f"handwritten revision taken as governing.")
            y = 0.20 + (r.row_index / max(len(out.rows), 1)) * 0.52
            lines.append(RawLine(
                vendor_label=r.vendor_label, rate=r.rate, currency=r.currency,
                basis=r.basis, dimensions_seen=r.dimensions_seen,
                dimension_system=r.dimension_system, confidence=conf,
                confidence_reason=reason,
                evidence=EvidenceRef(
                    evidence_id=f"{doc.vendor_id}-row{r.row_index}", doc_id=doc.doc_id,
                    locator=f"crop:0.14,{y:.3f},0.74,0.032",
                    bbox=f"0.14,{y:.3f},0.74,0.032")))

        return RawSubmission(
            vendor_id=doc.vendor_id, doc_id=doc.doc_id,
            stated_basis=out.stated_basis, document_terms=out.document_terms,
            injection_attempts=out.injection_attempts,
            extraction_notes=out.extraction_notes + out.legibility_notes, lines=lines)
