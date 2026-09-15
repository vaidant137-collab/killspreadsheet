"""
Contracts — the ONLY thing every module shares.

Rule: no module imports another module. They all import from here.
The moment `analyst/` imports from `extract/`, the seam is gone.

These models describe the buyer's side of the world: the RFx, its line items,
and the questionnaire. Vendor submissions live in contracts/quote.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Uom(str, Enum):
    """Buyer-side unit of measure. The whole normalisation problem lives here."""

    PIECE = "piece"
    KG = "kg"
    SET = "set"
    HUNDRED = "100_pieces"


def uom_label(uom) -> str:
    """How a unit of measure is written on screen and in the memo.

    Small, and it matters more than its size suggests: this dataset prices in
    pieces, kilograms, sets and hundreds of pieces, and a rate column that shows
    8.03 next to 1,339.00 with no unit anywhere invites exactly the comparison
    this whole project exists to stop. The 1,339 is a layer pad per HUNDRED.
    """
    return {"piece": "pcs", "kg": "kg", "set": "sets",
            "100_pieces": "\u00d7100 pcs"}.get(
                getattr(uom, "value", uom), str(getattr(uom, "value", uom)))


class BoxStyle(str, Enum):
    """FEFCO codes. 0201 = Regular Slotted Container, 0203 = Half Slotted,
    0427 = die-cut mailer. Sheets and pads have no FEFCO style."""

    RSC_0201 = "0201"
    HSC_0203 = "0203"
    DIECUT_0427 = "0427"
    SHEET = "sheet"
    PAD = "pad"
    PARTITION = "partition"


class Dimensions(BaseModel):
    length_mm: int
    width_mm: int
    height_mm: int | None = None  # sheets and pads are 2-D

    def label(self) -> str:
        if self.height_mm is None:
            return f"{self.length_mm}x{self.width_mm} mm"
        return f"{self.length_mm}x{self.width_mm}x{self.height_mm} mm"


class RfxLine(BaseModel):
    """One line of the buyer's bill of materials.

    `unit_weight_g` is the bridge fact that converts a per-kg quote into a
    per-piece price. It is deliberately NULL on lines the buyer has never
    bought before — that is not missing data, it is the honest state of a
    real procurement file, and it is what forces the 'unresolved' cell state.
    """

    line_no: int
    code: str
    description: str
    style: BoxStyle
    ply: int | None = None
    dims: Dimensions
    flute: str | None = None
    liner_gsm: int | None = None
    bursting_factor: int | None = None
    print_spec: str = "plain"
    annual_qty: int
    uom: Uom
    unit_weight_g: float | None = None
    food_contact: bool = False
    requires_tooling: bool = False
    introduced_this_year: bool = False

    # --- fields taken from real published tender practice --------------------
    # Indian tenders specify GSM as a per-layer stack, not one liner figure:
    # "150/150/150/150/150 (out to In)" (HAL tender MAT/P/B-12/263). A vendor
    # replying with a single number has not answered the question, and
    # comparing "180" against a stack compares nothing.
    gsm_stack: str | None = None

    # The same tender specifies THREE strength measures at once — bursting
    # strength in kg/cm2, bursting factor, and compression in kg — using "Ntl"
    # and "Nlt" interchangeably for "not less than", in the same document.
    # A vendor answering any one of the three looks compliant.
    strength_spec: dict[str, str] = Field(default_factory=dict)

    # "Two 3-ply B-grade plates per box" — one buyer line is really two
    # products. A vendor who prices the plates separately has not quoted
    # higher, they have quoted differently.
    sub_components: list[str] = Field(default_factory=list)

    # Buyers routinely identify a box by what goes in it rather than by its
    # board: "(1 Ltr. Humaur)", "5-10 Kg", "Above 45 kg".
    capacity_band: str | None = None


class QuestionnaireItem(BaseModel):
    q_no: int
    question: str
    answer_type: Literal["yes_no", "text", "number", "date"]
    gating: bool = False
    note: str | None = None


class Rfx(BaseModel):
    rfx_id: str
    title: str
    buyer_org: str
    category: str
    currency: str
    issued_date: str
    response_due: str
    award_target: str
    delivery_point: str
    required_incoterm: str
    required_payment_terms: str
    cost_of_capital_pct: float = Field(
        9.0, description="Used to NPV-adjust differing payment terms"
    )
    lines: list[RfxLine]
    questionnaire: list[QuestionnaireItem]


class PriorContractLine(BaseModel):
    """Last year's awarded rates. Needed to resolve incumbent quotes that say
    'rest same as last year' — which is not laziness, it is how incumbents quote."""

    line_no: int
    rate_inr: float
    uom: Uom


class RfxDraft(BaseModel):
    """The RFx while the buyer is still talking it into existence.

    Every field here is a decision the buyer makes in conversation, and every
    one of them changes the comparison that comes back. That is the point. If
    authoring were cosmetic — a nice conversation that produced the same table
    whatever you said — it would be theatre, and the brief is explicit that the
    AI loops must be real.

    What actually moves downstream:
      payment_terms_days  every landed cost is NPV-adjusted to these terms, so
                          moving 45 -> 30 re-prices all 139 cells
      line_nos            the schedule that goes out, and therefore the table,
                          the totals and which splits are feasible
      vendor_ids          who is invited, and so who can win
      gating_q_nos        which questionnaire answers disqualify. Un-gate the
                          quality-escape question and a disqualified vendor
                          comes back into contention

    What is stubbed, and stated as stubbed on screen: the mail does not leave
    the building. The brief allows exactly this ("fake the SMTP server if you
    like") and nothing else here is faked.
    """

    buyer_org: str | None = None
    category: str | None = None
    delivery_point: str | None = None
    required_incoterm: str | None = None
    payment_terms_days: int | None = None
    cost_of_capital_pct: float | None = None
    response_due: str | None = None

    line_nos: list[int] = Field(default_factory=list)
    # The item master is what the buyer HAS bought, not what they are buying
    # this year. A tender where the quantities cannot move, and where a line
    # bought for the first time cannot be added, is a picker rather than an RFx.
    # Overrides are per line and the master is never edited: next year's buyer
    # starts from the same catalogue.
    qty_overrides: dict[int, int] = Field(default_factory=dict)
    extra_lines: list[dict] = Field(default_factory=list)
    question_nos: list[int] = Field(default_factory=list)
    # The buyer has been through the questionnaire, whatever they kept. Without
    # this the server cannot tell "not decided yet" from "decided on four", and
    # a buyer who removed five questions had all nine put back for them — which
    # is what the mail then said was going out.
    questions_chosen: bool = False
    gating_q_nos: list[int] = Field(default_factory=list)
    vendor_ids: list[str] = Field(default_factory=list)

    mail_subject: str | None = None
    mail_body: str | None = None
    # The buyer clicked Approve on the covering mail. Not a formality: without
    # it the co-pilot could draft a mail and issue it in the same breath, and
    # "a mail they approve" would be a claim in a README rather than a step
    # anyone takes. issue_rfx refuses until this is true.
    mail_approved: bool = False
    issued: bool = False

    def missing(self) -> list[str]:
        """What still has to be decided before this can go to vendors.

        Named rather than defaulted: silently filling in payment terms is how a
        buyer ends up with quotes they cannot compare and no idea why.
        """
        gaps = []
        if not self.line_nos:
            gaps.append("a line schedule")
        if not self.vendor_ids:
            gaps.append("a vendor list")
        if self.payment_terms_days is None:
            gaps.append("payment terms")
        if not self.question_nos and not self.questions_chosen:
            gaps.append("a questionnaire")
        return gaps
