"""
Contracts — vendor side.

`GroundTruth` is the single source of truth for the whole demo. The five vendor
documents are *rendered from it*, which means the eval gold set is free: we are
never labelling documents after the fact, we are comparing extraction back
against the thing the documents were made from.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

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
    # The vendor priced the box but not the fitments the buyer's line includes.
    # Not a cheaper quote — a different one.
    excludes_sub_component: bool = False
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
    # Confirmed against ~45 live IndiaMART listings: Indian suppliers quote
    # dimensions in inches at least as often as millimetres, rounded, while
    # tenders specify mm. Converting "18x14x12 in" back to "450x350x300 mm" is
    # not arithmetic — it is fuzzy matching against a rounding already applied.
    dimension_system: str = "mm"          # "mm" | "inch"
    # "Per Box" and "Per Piece" are used interchangeably in the same category
    # on the same page. A matcher keyed on the string treats them as different.
    unit_wording: str = "Nos"
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


class Clarification(BaseModel):
    """Round two: what a vendor sends back when the buyer writes again.

    A tender is not a batch job. Five replies arrive, three of them are missing
    something the comparison needs, and what a buyer actually does is write
    back. This is that second reply — a real document with real content, so the
    cells it resolves are resolved by a vendor rather than by a guess.

    Each field answers a specific kind of gap:
      unit_weights_g   a per-kilogram quote cannot become a per-piece price
                       without the weight of the piece
      questionnaire    a corrected or evidenced answer — an expired certificate
                       replaced by a current one re-qualifies a vendor
      moq_pieces       a revised minimum order, when the first one blocked lines
      line_quotes      rates for lines they did not price the first time
    """

    vendor_id: str
    asked_for: list[str] = Field(default_factory=list)
    reply_text: str = ""
    received_at: str = ""
    unit_weights_g: dict[int, float] = Field(default_factory=dict)
    questionnaire: list[QuestionnaireAnswer] = Field(default_factory=list)
    moq_pieces: int | None = None
    line_quotes: list[VendorLineQuote] = Field(default_factory=list)
    # A replacement document. Re-answering a question is not the same as
    # sending the certificate: the gate reads the attachment, so a vendor whose
    # paperwork has been renewed has to send the paperwork.
    attachments: list[Attachment] = Field(default_factory=list)
    declined: str | None = None


class GroundTruth(BaseModel):
    rfx: Rfx
    prior_contract: list[PriorContractLine]
    submissions: list[VendorSubmission]
    # Keyed by vendor. Absent means that vendor has nothing to clarify, which is
    # itself information: Shakti quoted on the buyer's own basis and there is
    # nothing to ask them.
    clarifications: list[Clarification] = Field(default_factory=list)

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
