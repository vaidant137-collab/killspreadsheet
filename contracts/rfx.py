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
