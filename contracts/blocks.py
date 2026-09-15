"""
Blocks — the seam between the agent and the screen.

This is the most important contract in the system. As long as the analyst emits
Blocks, the entire analyst can be replaced — hand-written loop, LangGraph,
anything — and the interface does not move. And because the UI consumes only
these shapes, it never has to know a model exists.

Every block that carries a number also carries how that number was obtained.
There is no block type for "a figure the model asserted".
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Column(BaseModel):
    key: str
    label: str
    align: Literal["left", "right"] = "left"
    numeric: bool = False


class Cell(BaseModel):
    """A value plus its epistemic status. The three states are not styling —
    they are the reason a buyer can act on this screen."""

    value: str | float | int | None = None
    state: Literal["extracted", "derived", "unresolved", "plain"] = "plain"
    evidence_id: str | None = None
    note: str | None = None
    confidence: float | None = None


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[Column]
    rows: list[dict[str, Cell]]
    footnotes: list[str] = Field(default_factory=list)
    # When true the UI mutates the pinned comparison in place rather than
    # appending a new table to the transcript. The brief asks for "a single
    # side-by-side comparison"; a stream of stale copies is not that.
    pin: bool = False


class Series(BaseModel):
    label: str
    values: list[float]


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    kind: Literal["bar", "line", "grouped_bar"] = "bar"
    title: str
    categories: list[str]
    series: list[Series]
    unit: str = "INR"
    # Drawn only from rows a tool returned. A chart the model populated from
    # memory would look identical and mean nothing.
    source_query: str | None = None


class EvidenceBlock(BaseModel):
    type: Literal["evidence"] = "evidence"
    evidence_id: str
    doc_id: str
    locator: str
    caption: str
    snippet: str | None = None


class ReviewCard(BaseModel):
    review_id: int
    vendor_id: str
    line_no: int | None
    field: str
    proposed_value: str | None
    confidence: float
    evidence_id: str | None
    reason: str | None = None


class ReviewBlock(BaseModel):
    type: Literal["review"] = "review"
    title: str
    cards: list[ReviewCard]
    remaining: int = 0


class AssumptionRow(BaseModel):
    key: str
    label: str
    value: str
    unit: str | None = None
    source: str
    editable: bool = True


class AssumptionBlock(BaseModel):
    type: Literal["assumptions"] = "assumptions"
    title: str = "Assumptions in force"
    rows: list[AssumptionRow]
    note: str | None = None


class QueryBlock(BaseModel):
    """The query that produced the answer, collapsed by default.

    A buyer who wants to check can check; a VP who wants to challenge has
    something to challenge. An answer with no query behind it is an assertion.
    """

    type: Literal["query"] = "query"
    sql: str | None = None
    code: str | None = None
    row_count: int = 0


class RefusalBlock(BaseModel):
    """Not an error. A product surface.

    Used when the data cannot support the question — "which vendor is most
    reliable" needs delivery history, quality escapes and OTIF data, none of
    which is in an RFx. Naming what is missing is a better answer than a
    confident guess, and it is the thing that makes the other answers credible.
    """

    type: Literal["refusal"] = "refusal"
    question: str
    reason: str
    would_need: list[str] = Field(default_factory=list)


class OptionCard(BaseModel):
    kind: str                       # cheapest | fastest | single
    label: str
    why: str
    strategy: str
    vendors: list[str] = Field(default_factory=list)
    vendor_names: list[str] = Field(default_factory=list)
    total_inr: float = 0.0
    line_value_inr: float = 0.0
    freight_inr: float = 0.0
    tooling_inr: float = 0.0
    lead_time_days: int | None = None
    lines_covered: int = 0
    lines_total: int = 0
    feasible: bool = True
    violations: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class OptionsBlock(BaseModel):
    """The three shapes of answer, before any question is asked.

    A comparison grid is a means; nobody awards a contract from one. What a
    category manager decides between is cheapest, fastest, and one-throat-to-
    choke — so lead with those, with the cost of each and the reason it might
    not be on the table at all. Ending at the table is why the spreadsheet
    survives.
    """

    type: Literal["options"] = "options"
    title: str = "Three ways to award this"
    cards: list[OptionCard] = Field(default_factory=list)
    note: str | None = None


class DraftField(BaseModel):
    label: str
    value: str
    changes: str | None = None      # what this decision moves downstream


class RfxDraftBlock(BaseModel):
    """The RFx as it stands mid-conversation.

    Re-rendered after every decision rather than described in prose, because a
    buyer agreeing to terms they cannot see is how the wrong RFx goes out. Each
    field carries what it CHANGES, so the buyer can tell a cosmetic choice from
    one that re-prices the whole schedule.
    """

    type: Literal["rfx_draft"] = "rfx_draft"
    title: str = "RFx — draft"
    fields: list[DraftField] = Field(default_factory=list)
    lines_included: int = 0
    lines_available: int = 0
    questions_included: int = 0
    gating: list[str] = Field(default_factory=list)
    vendors: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    ready: bool = False


class MailDraftBlock(BaseModel):
    """The covering mail, drafted for approval and not sent until approved.

    The send is stubbed and says so on its face. That is the one stub the brief
    permits, and the honest thing is to label it rather than let a viewer
    assume mail left the building.
    """

    type: Literal["mail_draft"] = "mail_draft"
    to: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    attachments: list[str] = Field(default_factory=list)
    stub_note: str = ("Approving this does not send mail. The SMTP path is "
                      "stubbed; the five vendor replies are documents that "
                      "already exist, and the RFx you just authored decides "
                      "which lines, terms and gates they are read against.")


# typing.Union rather than `X | Y`, because this is a RUNTIME expression, not
# an annotation. `from __future__ import annotations` defers annotations to
# strings but does nothing for an assignment like this one, and `|` between
# classes is only valid from Python 3.10. macOS still ships 3.9.
Block = Union[TextBlock, TableBlock, ChartBlock, EvidenceBlock, ReviewBlock,
              AssumptionBlock, QueryBlock, RefusalBlock, RfxDraftBlock,
              MailDraftBlock, OptionsBlock]
