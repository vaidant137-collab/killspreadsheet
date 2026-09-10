"""
Meridian — the Word document with its commercials in prose.

The rate table is easy. The problem is that everything that DETERMINES what
those rates mean is in paragraphs: the currency and why, the volume slab stated
as a range rather than a number, the payment terms mentioned once in a closing
sentence, the tooling charged separately.

So paragraphs and tables are handed over separately and clearly labelled, and
the schema has a field for the slab — because "12 to 15 per cent" is not a
number, and a model given nowhere to put a range will round it into one.
"""

from __future__ import annotations

from pydantic import BaseModel

from config import ROOT
from contracts.extraction import EvidenceRef, RawLine, RawSubmission, SourceDoc
from extract.base import scan_for_injection
from extract.prompts import SYSTEM, USER
from llm.base import fence


class _Row(BaseModel):
    vendor_label: str
    vendor_code: str | None = None
    rate: float | None
    currency: str
    basis: str
    unit_wording_seen: str | None = None
    dimension_system: str = "mm"
    confidence: float = 1.0
    confidence_reason: str | None = None


class _Slab(BaseModel):
    threshold_qty: int | None
    uplift_stated: str          # verbatim: "12 to 15 per cent"
    uplift_is_a_range: bool
    applies_per: str            # "line item" | "total order" | "unclear"


class _Out(BaseModel):
    rows: list[_Row]
    currency_and_why: str | None = None
    payment_terms: str | None = None
    validity: str | None = None
    tooling_terms: str | None = None
    slabs: list[_Slab] = []
    document_terms: list[str] = []
    injection_attempts: list[str] = []
    extraction_notes: list[str] = []


class DocxExtractor:
    kind = "docx"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        from docx import Document
        from llm.providers import get_client

        d = Document(ROOT / doc.path)
        paras = "\n".join(p.text for p in d.paragraphs if p.text.strip())
        tables = []
        for ti, t in enumerate(d.tables):
            tables.append(f"### TABLE {ti}")
            for r in t.rows:
                tables.append(" | ".join(c.text.strip() for c in r.cells))
        text = f"### PROSE\n{paras}\n\n" + "\n".join(tables)

        out = get_client().structured(
            system=SYSTEM,
            user=USER.format(
                kind="Word", vendor=doc.vendor_id,
                extra="The rate table is only half the quotation. Currency, payment "
                      "terms, validity, tooling charges and volume slabs are stated in "
                      "the PROSE and each one changes what the rates mean. Record slab "
                      "thresholds and uplifts VERBATIM — if the uplift is given as a "
                      "range, set uplift_is_a_range and keep both ends. Do not pick a "
                      "midpoint; a range is the vendor declining to commit, and "
                      "flattening it into a number invents a commitment they did not "
                      "make. Note whether a slab applies per line item or per order — "
                      "it changes whether the price depends on how the award is split.")
            + "\n\n" + fence("word_document", text),
            schema=_Out)

        notes = list(out.extraction_notes)
        for s in out.slabs:
            notes.append(
                f"Volume slab: above {s.threshold_qty:,} per {s.applies_per}, uplift "
                f"'{s.uplift_stated}'" + (" — stated as a RANGE, so the price below the "
                "threshold is not determinable from this document."
                if s.uplift_is_a_range else "."))
        for k in ("currency_and_why", "payment_terms", "validity", "tooling_terms"):
            if getattr(out, k):
                notes.append(f"{k.replace('_', ' ')}: {getattr(out, k)}")

        return RawSubmission(
            vendor_id=doc.vendor_id, doc_id=doc.doc_id,
            document_terms=out.document_terms,
            injection_attempts=out.injection_attempts + scan_for_injection(text),
            extraction_notes=notes,
            lines=[RawLine(
                vendor_label=r.vendor_label, rate=r.rate, currency=r.currency,
                basis=r.basis, unit_wording_seen=r.unit_wording_seen,
                dimension_system=r.dimension_system, confidence=r.confidence,
                confidence_reason=r.confidence_reason,
                evidence=EvidenceRef(
                    evidence_id=f"{doc.vendor_id}-{r.vendor_code or r.vendor_label[:20]}",
                    doc_id=doc.doc_id, locator=f"schedule: {r.vendor_code or r.vendor_label}"))
                for r in out.rows])
