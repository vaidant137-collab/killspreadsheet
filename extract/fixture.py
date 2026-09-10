"""
Fixture extraction — replay, not fake.

This replays what a correct extractor WOULD have read out of each document,
expressed the way that document expresses it: the vendor's own label, the
vendor's own unit, the vendor's own dimension system. It does not hand over
buyer line numbers, so the matcher still has to do its job for real.

That distinction matters. The fixture fakes OCR and parsing — the part a model
does. It does not fake matching, normalisation, allocation or the analyst, all
of which run on this output exactly as they will on real extraction.

Confidences are not all 1.0. The photograph's shadow band genuinely degrades
four rows and the pen revisions genuinely obscure two, so those rows carry the
confidence a real reader would report — which means the review queue has real
work in it before any model has run.
"""

from __future__ import annotations

import json

from config import DATA
from contracts.extraction import EvidenceRef, RawLine, RawSubmission, SourceDoc
from contracts.quote import GroundTruth
from tools.labels import ganesh, meridian_desc, nova, shakti

_LABELLERS = {"shakti": shakti, "nova": nova, "meridian": meridian_desc, "ganesh": ganesh}

# Rows the photographer's shadow falls across, and the two revised in pen.
# These are properties of the image, not of the data.
GANESH_SHADOW_ROWS = {19, 20, 21, 22}
GANESH_PEN_ROWS = {6, 14}

_DOC_FOR = {
    "shakti": "shakti_quotation_SPPL-QT-2026-27-0318.xlsx",
    "nova": "nova_quotation_NCPL-2026-27-Q-0912.pdf",
    "meridian": "meridian_offer_MPI-EXP-2026-1184.docx",
    "ganesh": "ganesh_rate_card_photo.jpg",
    "apex": "apex_reply.eml",
}


def _gt() -> GroundTruth:
    return GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))


def _locator(vid: str, row: int, ln) -> tuple[str, str | None]:
    if vid == "shakti":
        return f"Rate Working!L{row + 1}", None
    if vid == "nova":
        return f"p{1 if row <= 14 else 2}", None
    if vid == "meridian":
        return f"table row {row}", None
    if vid == "ganesh":
        y = 0.20 + (row / 22) * 0.52
        return f"crop:0.14,{y:.3f},0.74,0.032", None
    return "body", None


class FixtureExtractor:
    kind = "fixture"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        gt = _gt()
        sub = next(s for s in gt.submissions if s.vendor.vendor_id == doc.vendor_id)
        lines = {l.line_no: l for l in gt.rfx.lines}
        vid = doc.vendor_id
        out = RawSubmission(vendor_id=vid, doc_id=doc.doc_id,
                            document_terms=list(sub.freeform_terms),
                            currency_seen=sub.vendor.currency)

        if vid == "ganesh":
            out.stated_basis = "ALL RATES PER 100 BOX.  SIZES IN INCH.  EX-WORKS AMBERNATH.  GST EXTRA."
        elif vid == "shakti":
            out.stated_basis = "Ex-works Bhiwandi. GST 18% extra. Validity 15 days."
        elif vid == "nova":
            out.stated_basis = "FOR Bhiwandi DC, inclusive of GST. Payment 45 days from GRN."
        elif vid == "meridian":
            out.stated_basis = "Rates in USD, ex-works Chennai. GST extra. Payment 90 days from B/L."
        elif vid == "apex":
            out.stated_basis = "Rs 42/kg for the 5-ply, 38 for the 3-ply, rest same as last year, freight extra."

        if vid == "apex":
            # The incumbent's email has no line schedule at all. It states three
            # things: a rate for 5-ply board, a rate for 3-ply board, and a
            # pointer to last year's contract for everything else. Pretending it
            # yielded thirty rows would be inventing structure the document does
            # not have -- and would hide the actual problem, which is that these
            # rates apply to CLASSES of lines, not to items.
            for ply, rate in ((5, 42.0), (3, 38.0)):
                out.lines.append(RawLine(
                    vendor_label=f"{ply}-ply board (all items)", rate=rate,
                    currency="INR", basis="per_kg", unit_wording_seen="per kg",
                    confidence=0.86,
                    confidence_reason="Rate is stated against a ply grade, not against "
                                      "any named item; which lines it covers is inferred",
                    evidence=EvidenceRef(evidence_id=f"apex-ply{ply}",
                                         doc_id=_DOC_FOR["apex"], locator="body line 3",
                                         snippet=f"Rs {rate:.0f}/kg for the {ply}-ply")))
            out.lines.append(RawLine(
                vendor_label="rest same as last year", rate=None, currency="INR",
                basis="per_piece", refers_to_prior_contract=True, confidence=0.80,
                confidence_reason="A pointer to a prior document, not a price",
                note="rest same as last year",
                evidence=EvidenceRef(evidence_id="apex-prior", doc_id=_DOC_FOR["apex"],
                                     locator="body line 3",
                                     snippet="rest same as last year, freight extra")))
            out.extraction_notes.append(
                'The email prices BOARD by ply. Converting to a price per piece needs '
                'a unit weight, and "rest same as last year" resolves only against the '
                "attached FY26 rate contract.")
            return out

        for row, q in enumerate(sub.line_quotes, start=1):
            ln = lines[q.line_no]
            conf, reason = 1.0, None

            if vid == "ganesh":
                if row in GANESH_SHADOW_ROWS:
                    conf, reason = 0.61, ("Row falls under the photographer's shadow; "
                                          "contrast and sharpness are materially reduced")
                elif row in GANESH_PEN_ROWS:
                    conf, reason = 0.74, ("Printed rate is struck through and a handwritten "
                                          "revision is written beside it")
                else:
                    conf = 0.93
            elif vid == "meridian":
                conf = 0.88 if q.line_no in (27, 28, 29, 30) else 0.96
                if conf < 0.9:
                    reason = "Fitment described in prose; unit basis inferred from the schedule"
            elif vid == "apex":
                conf, reason = 0.70, ("No line schedule in the email; the rate applies to a "
                                      "ply grade, not to a named item")
            elif vid == "shakti":
                conf = 0.99
            elif vid == "nova":
                conf = 0.97

            label = (_LABELLERS[vid](ln) if vid in _LABELLERS
                     else f"{ln.ply}-ply board" if ln.ply else ln.description)
            loc, snip = _locator(vid, row, ln)
            out.lines.append(RawLine(
                vendor_label=label, rate=q.rate, currency=q.currency, basis=q.basis.value,
                unit_wording_seen=sub.vendor.unit_wording,
                dimension_system=sub.vendor.dimension_system,
                note=q.note, refers_to_prior_contract=q.refers_to_prior_contract,
                tooling_inr=q.tooling_inr, tooling_amortised=q.tooling_amortised,
                confidence=conf, confidence_reason=reason,
                evidence=EvidenceRef(
                    evidence_id=f"{vid}-{q.line_no}", doc_id=_DOC_FOR[vid],
                    locator=loc, snippet=snip)))

        if vid == "ganesh":
            out.extraction_notes.append(
                "The rate card states the vendor does not supply 7-ply export cartons "
                "or sheets, while their company profile advertises 7-ply at "
                "Rs 96-240/box. The rate card is the quote; the brochure is not a bid.")
        return out
