"""
Contracts for the deterministic half: normalisation and allocation.

Nothing in this file is produced by a model. Landed cost is computed in Python,
from extracted values plus stated assumptions, because the moment a model does
the arithmetic nothing on screen is auditable and the Rs 4-crore question
answers itself in the wrong direction.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from contracts.rfx import Uom


class CellState(str, Enum):
    """The three states, and there are only three.

    The system never invents a number it will then compare on. A cell is either
    something a vendor actually said, something we computed under an assumption
    we can name, or a gap we refuse to fill.
    """

    EXTRACTED = "extracted"      # read verbatim; no conversion applied
    DERIVED = "derived"          # computed under stated, editable assumptions
    UNRESOLVED = "unresolved"    # a required fact is missing; we will not guess


class Assumption(BaseModel):
    """A row in the assumptions panel. Every derived number names the ones it
    used, and changing one re-ranks the comparison live."""

    key: str
    label: str
    value: float | str
    unit: str | None = None
    source: str
    editable: bool = True


class NormalisedLine(BaseModel):
    vendor_id: str
    line_no: int
    buyer_uom: Uom

    as_quoted: str                       # what the vendor literally said
    landed_inr: float | None             # per buyer UOM, pre-tax, NPV-adjusted
    state: CellState

    assumptions_used: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    unresolved_reason: str | None = None
    missing_fact: str | None = None      # names the ONE thing needed to resolve

    # Components, so the drill-down can show the arithmetic rather than assert it
    base_inr: float | None = None
    freight_inr: float | None = None
    tooling_inr: float | None = None
    discount_inr: float | None = None
    npv_adjustment_inr: float | None = None

    evidence_ref: str | None = None
    extraction_confidence: float = 1.0
    match_confidence: float = 1.0

    @property
    def needs_review(self) -> bool:
        from config import REVIEW_THRESHOLD
        return min(self.extraction_confidence, self.match_confidence) < REVIEW_THRESHOLD


class VendorTotals(BaseModel):
    vendor_id: str
    lines_quoted: int
    lines_resolved: int
    lines_unresolved: int
    covered_annual_value_inr: float
    qualified: bool
    disqualified_because: list[str] = Field(default_factory=list)


class LineAward(BaseModel):
    line_no: int
    vendor_id: str | None
    unit_inr: float | None
    annual_qty: int
    annual_inr: float | None
    uncovered_reason: str | None = None


class Allocation(BaseModel):
    """The output of any allocator. `naive`, `subsets` and a future `milp` all
    return this, which is why swapping them changes nothing else."""

    strategy: str
    vendors_used: list[str]
    awards: list[LineAward]
    line_value_inr: float
    freight_inr: float
    tooling_inr: float
    total_inr: float
    feasible: bool
    violations: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    uncovered_lines: list[int] = Field(default_factory=list)
