"""
Contracts — vendor side.

`GroundTruth` is the single source of truth for the whole demo. The five vendor
documents are *rendered from it*, which means the eval gold set is free: we are
never labelling documents after the fact, we are comparing extraction back
against the thing the documents were made from.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from contracts.rfx import PriorContractLine, Rfx, Uom


class QuoteBasis(str, Enum):
    """How the vendor priced it. Almost never the same as the buyer's UOM."""

    PER_PIECE = "per_piece"
    PER_KG = "per_kg"
    PER_100 = "per_100_pieces"
    PER_SET = "per_set"


class Incoterm(str, Enum):
    EX_WORKS = "ex_works"
    FOR_DESTINATION = "for_destination"
    FREIGHT_EXTRA = "freight_extra"


class TaxBasis(str, Enum):
    GST_EXTRA = "gst_extra"
    GST_INCLUDED = "gst_included"


class VendorLineQuote(BaseModel):
    """What a vendor actually quoted for one of the buyer's lines.

    Note there is no `landed_cost` field. Landed cost is *derived*, in
    normalize/, deterministically, and it carries its assumptions with it.
    Nothing a model returns is ever allowed to be a landed cost.
    """

    line_no: int
    # None means "the vendor referred us elsewhere" (e.g. 'rest same as last
    # year'). It is NOT zero and it is NOT a no-quote. Collapsing those three
    # into one empty cell is the spreadsheet bug this whole system exists to
    # kill, so the type keeps them apart.
    rate: float | None
    currency: str
    basis: QuoteBasis
    refers_to_prior_contract: bool = False
    tooling_inr: float | None = None
    tooling_amortised: bool = False
    note: str | None = None


class VolumeSlab(BaseModel):
    """Price depends on awarded volume, which depends on the split, which
    depends on price. Circular by nature — resolved in allocate/ by iterating
    to a fixed point, not by lookup."""

    min_qty: int
    uplift_pct: float


class QuestionnaireAnswer(BaseModel):
    q_no: int
    answer: str
    evidence_file: str | None = None
    contradicted_by_evidence: bool = False


class Attachment(BaseModel):
    filename: str
    kind: str
    valid_until: str | None = None
    summary: str


class VendorProfile(BaseModel):
    vendor_id: str
    name: str
    city: str
    incumbent: bool = False
    reply_format: str
    currency: str
    incoterm: Incoterm
    tax_basis: TaxBasis
    payment_days: int
    validity_days: int | None = None
    early_payment_discount_pct: float | None = None
    early_payment_within_days: int | None = None
    moq_pieces: int
    slabs: list[VolumeSlab] = []
    fx_rate_at_quote: float | None = None
    freight_inr_per_shipment: float | None = None
    shipments_per_year: int = 12


class VendorSubmission(BaseModel):
    """The gold-standard content of one vendor's reply. The renderer turns this
    into an XLSX / PDF / DOCX / photo / email; the extractor's job is to get
    back to it."""

    vendor: VendorProfile
    line_quotes: list[VendorLineQuote]
    questionnaire: list[QuestionnaireAnswer]
    attachments: list[Attachment] = []
    freeform_terms: list[str] = []


class GroundTruth(BaseModel):
    rfx: Rfx
    prior_contract: list[PriorContractLine]
    submissions: list[VendorSubmission]

    def line(self, line_no: int):
        return next(l for l in self.rfx.lines if l.line_no == line_no)


__all__ = [
    "QuoteBasis",
    "Incoterm",
    "TaxBasis",
    "VendorLineQuote",
    "VolumeSlab",
    "QuestionnaireAnswer",
    "Attachment",
    "VendorProfile",
    "VendorSubmission",
    "GroundTruth",
    "Uom",
]
