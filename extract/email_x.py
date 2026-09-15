"""
Apex — the incumbent's four-line email.

The hardest document in the set and the shortest, because it fails in three ways
at once and each needs a different resolution:

  "Rs 42/kg for the 5-ply"    prices BOARD; the buyer buys PIECES
  "rest same as last year"    a pointer to a document, not a price
  "freight extra"             leaves the Incoterm undeclared

The schema refuses to let any of those be smoothed over. A rate that applies to
a ply grade is recorded as covering a CLASS, not as thirty invented rows. A
pointer is recorded as a pointer, with rate left null — never zero.
"""

from __future__ import annotations


from pydantic import BaseModel

from config import ROOT
from contracts.extraction import EvidenceRef, RawLine, RawSubmission, SourceDoc
from extract.base import scan_for_injection
from extract.prompts import SYSTEM, USER


class _ClassRate(BaseModel):
    """A rate stated against a grade of material rather than against any item."""
    applies_to: str = ""             # "5-ply board"
    rate: float
    currency: str = "INR"
    basis: str = "per_piece"                  # per_kg
    quoted_text: str = ""


class _Pointer(BaseModel):
    """A reference to another document instead of a price."""
    text: str = ""                   # "rest same as last year"
    refers_to: str = ""              # "FY26 rate contract"
    covers: str = ""                 # what it appears to cover


class _Out(BaseModel):
    class_rates: list[_ClassRate] = []
    pointers: list[_Pointer] = []
    itemised_rows: list[dict] = []
    incoterm_stated: str | None = None
    validity_stated: str | None = None
    injection_attempts: list[str] = []
    extraction_notes: list[str] = []


class EmailExtractor:
    kind = "email"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        from llm.providers import get_client
        text = (ROOT / doc.path).read_text(encoding="utf-8", errors="replace")

        out = get_client().structured(
            system=SYSTEM,
            user=USER.format(
                kind="email", vendor=doc.vendor_id,
                extra="This email may contain NO itemised schedule at all. Do not "
                      "manufacture one.\n\n"
                      "- A rate given against a material grade ('Rs 42/kg for the "
                      "5-ply') applies to a CLASS of items, not to one item. Record it "
                      "in class_rates. Do not expand it into rows; which lines it "
                      "covers is somebody else's decision, made with the buyer's "
                      "schedule in hand.\n"
                      "- A phrase like 'rest same as last year' is a POINTER to another "
                      "document, not a price. Record it in pointers with rate absent. "
                      "It is not zero.\n"
                      "- Note whether an Incoterm and a validity period were stated at "
                      "all. Silence is a finding: this quote may have no expiry.")
            + "\n\n<email trust=\"untrusted\">\n" + text + "\n</email>",
            schema=_Out)

        lines: list[RawLine] = []
        for c in out.class_rates:
            lines.append(RawLine(
                vendor_label=f"{c.applies_to} (all items)", rate=c.rate,
                currency=c.currency, basis=c.basis, unit_wording_seen="per kg",
                confidence=0.86,
                confidence_reason="Rate is stated against a grade, not against any named "
                                  "item; which lines it covers is inferred",
                evidence=EvidenceRef(evidence_id=f"{doc.vendor_id}-{c.applies_to[:12]}",
                                     doc_id=doc.doc_id, locator="body",
                                     snippet=c.quoted_text)))
        for p in out.pointers:
            lines.append(RawLine(
                vendor_label=p.text, rate=None, currency="INR", basis="per_piece",
                refers_to_prior_contract=True, note=p.text, confidence=0.80,
                confidence_reason=f"A pointer to {p.refers_to}, not a price",
                evidence=EvidenceRef(evidence_id=f"{doc.vendor_id}-prior",
                                     doc_id=doc.doc_id, locator="body",
                                     snippet=p.text)))

        notes = list(out.extraction_notes)
        if not out.validity_stated:
            notes.append("No validity period is stated anywhere in this quotation.")
        if out.incoterm_stated:
            notes.append(f"Incoterm as stated: {out.incoterm_stated}")

        return RawSubmission(
            vendor_id=doc.vendor_id, doc_id=doc.doc_id, lines=lines,
            stated_basis=out.incoterm_stated,
            injection_attempts=out.injection_attempts + scan_for_injection(text),
            extraction_notes=notes)
