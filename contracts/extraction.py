"""
Contracts for the extraction and matching layers.

The critical separation: **an extractor never sees the buyer's template.**

It reads a vendor document into the VENDOR's own schema — their label, their
unit, their number — and stops. Matching to the buyer's line numbers is a
separate, later step with its own confidence score.

That separation exists because the two failures are different and only one of
them is visible. Hand a model a 30-row template and 27 rows of data and it will
helpfully invent three. And a 3-ply price matched onto a 5-ply line is a perfect
extraction with a catastrophic result — no extraction confidence catches it,
because nothing was mis-read.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SourceDoc(BaseModel):
    doc_id: str
    vendor_id: str
    path: str
    kind: str          # xlsx | pdf | docx | image | email
    role: str          # quote | questionnaire | evidence | brochure


class EvidenceRef(BaseModel):
    """Where a number came from, precisely enough to open it.

    Not a citation string — a locator the drawer can resolve to the actual
    page, cell, or region of the photograph.
    """

    evidence_id: str
    doc_id: str
    locator: str                    # "p3" | "Rate Working!L14" | "crop:x,y,w,h"
    snippet: str | None = None
    page: int | None = None
    bbox: str | None = None


class RawLine(BaseModel):
    """One priced row, in the vendor's own terms. No buyer line number yet."""

    vendor_label: str
    rate: float | None
    currency: str = "INR"
    basis: str                      # per_piece | per_kg | per_100_pieces | per_set
    unit_wording_seen: str | None = None
    dimensions_seen: str | None = None
    dimension_system: str = "mm"
    note: str | None = None
    refers_to_prior_contract: bool = False
    tooling_inr: float | None = None
    tooling_amortised: bool = False
    confidence: float = 1.0
    confidence_reason: str | None = None
    evidence: EvidenceRef | None = None


class RawSubmission(BaseModel):
    """Everything one document yielded, before any of it is matched."""

    vendor_id: str
    doc_id: str
    lines: list[RawLine] = Field(default_factory=list)
    document_terms: list[str] = Field(default_factory=list)
    stated_basis: str | None = None          # "ALL RATES PER 100 BOX. SIZES IN INCH."
    currency_seen: str = "INR"
    # Text that tried to instruct the reader rather than inform them. Logged and
    # surfaced to the buyer, because a supplier who attempted this is
    # information the buyer wants — not something to silently drop.
    injection_attempts: list[str] = Field(default_factory=list)
    extraction_notes: list[str] = Field(default_factory=list)

    # A model handed one note as a bare string rather than a list of one, and a
    # whole extraction run died on a pydantic list_type error. That is the model
    # being loosely right, not wrong — the content was correct and the container
    # was not — and the boundary should absorb it rather than discard five
    # documents' worth of real work.
    #
    # Note what this does NOT do: it never invents, splits, or reinterprets a
    # value. A string becomes a one-item list and nothing else changes, so the
    # guarantee that the system never invents a number it will compare on is
    # untouched. Everything past this point still validates strictly.
    @field_validator("document_terms", "injection_attempts", "extraction_notes",
                     mode="before")
    @classmethod
    def _one_string_is_a_list_of_one(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v


class LineMatch(BaseModel):
    vendor_label: str
    line_no: int | None
    confidence: float
    rationale: str
    alternatives: list[int] = Field(default_factory=list)


class ExtractedQuoteLine(BaseModel):
    """A raw line, matched. This is what reaches the store."""

    vendor_id: str
    line_no: int | None
    vendor_label: str
    rate: float | None
    currency: str
    basis: str
    refers_to_prior_contract: bool = False
    excludes_sub_component: bool = False
    tooling_inr: float | None = None
    tooling_amortised: bool = False
    note: str | None = None
    evidence: EvidenceRef | None = None
    extraction_confidence: float = 1.0
    match_confidence: float = 1.0
    match_rationale: str | None = None
