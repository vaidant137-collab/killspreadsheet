"""
The RFx co-pilot — the half of the product that happens before any vendor has
replied.

The brief opens with it: "A buyer *talks* an RFx into existence with an AI
co-pilot — scope, line items, questionnaire, terms." Starting a demo at the
comparison skips the first half of the story and, worse, hides the thing that
makes the second half interesting: the comparison is downstream of choices
somebody made, and most of the pain in it was authored in.

Same loop as `analyst/loop.py`, different tools and a different system prompt.
That is the whole reason blocks are a contract — two agents, one screen.

WHAT IS REAL HERE, AND WHAT IS STUBBED
--------------------------------------
Real: every decision the buyer makes is applied to the RFx that extraction,
normalisation and allocation then run against. Change payment terms from 45
days to 30 and all 139 landed costs are re-derived at the buyer's cost of
capital. Drop the quality-escape question from the gate and a disqualified
vendor comes back into contention. Choose twelve lines instead of thirty and
the feasible splits change.

Stubbed: the mail does not leave the building, and the five replies are
documents that already exist. The brief permits exactly this one stub. It is
labelled on screen rather than implied.

WHY ISSUING IS NOT DONE HERE
----------------------------
`issue_rfx` does not run the pipeline. It returns a signal, and the API layer —
which is a composition root and is allowed to know about everything — runs it.
If this module imported `pipeline`, the seam that lets the analyst be swapped
for LangGraph would be gone, and it would be gone in the least obvious
direction: a leaf importing the composition root.
"""

from __future__ import annotations

from contracts.blocks import DraftField, MailDraftBlock, RfxDraftBlock, TextBlock
from contracts.rfx import RfxDraft

AUTHOR_SYSTEM = """You are an RFx co-pilot working with a category buyer who is \
about to put roughly INR 11 crore of corrugated packaging out to tender. Your \
job is to turn what they tell you into a defensible RFx, and to make them decide \
the things that decide the outcome.

HOW YOU WORK

Call list_catalogue before proposing line items, questions or vendors. You do \
not know what is in the buyer's item master until you look, and inventing a line \
item they do not stock wastes everybody's tender.

PROPOSE, THEN CONFIRM. Make a concrete recommendation with a reason — "45-day \
terms, because that is what your incumbent contract runs on and quoting against \
anything else makes the responses non-comparable" — and let the buyer overrule \
it. A co-pilot that asks nine open questions in a row has made the buyer do the \
work.

THE FOUR THINGS THAT DECIDE THE ANSWER are the line schedule, payment terms, \
the vendor list, and which questionnaire answers are allowed to disqualify. \
Everything else is paperwork. Spend the conversation on those four.

SAY WHAT A CHOICE COSTS. Payment terms are not a formality: every rate that \
comes back is NPV-adjusted to them, so the terms you set determine who looks \
cheapest. Gating questions are a buyer policy, not a fact — gate on quality \
escapes and you may disqualify your lowest bidder. Name that at the time the \
buyer chooses, not afterwards.

BE BRIEF. You are talking to someone who has run tenders before. Two or three \
sentences per turn. Never restate the whole draft in prose — show_draft renders \
it, and it renders after every change automatically.

When the buyer is ready, draft_mail writes the covering note and issue_rfx sends \
it. Tell them plainly that the send is stubbed."""


# ---------------------------------------------------------------------------
# Tool specs. Deliberately narrow: each one sets a named part of the draft, so
# a wrong call is visible as a wrong field rather than a silently wrong RFx.
# ---------------------------------------------------------------------------

AUTHOR_TOOL_SPECS = [
    {"name": "list_catalogue",
     "description": "Look at what is available to put in the RFx: 'lines' is the "
                    "buyer's item master, 'questions' the standard quality "
                    "questionnaire, 'vendors' the approved supplier list. Call "
                    "this before proposing any of them.",
     "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["lines", "questions", "vendors"]}},
         "required": ["kind"]}},

    {"name": "set_header",
     "description": "Set the administrative header of the RFx.",
     "input_schema": {"type": "object", "properties": {
         "buyer_org": {"type": "string"},
         "category": {"type": "string"},
         "delivery_point": {"type": "string",
                            "description": "Named place, e.g. 'Bhiwandi DC'."},
         "required_incoterm": {"type": "string",
                               "description": "Incoterm WITH named place. Industry "
                                              "checklists call this the single most "
                                              "important comparability field."},
         "response_due": {"type": "string", "description": "ISO date."}}}},

    {"name": "choose_lines",
     "description": "Choose which item-master lines go out. Either 'all', or a "
                    "filter on ply/style, or explicit line numbers.",
     "input_schema": {"type": "object", "properties": {
         "mode": {"type": "string", "enum": ["all", "filter", "explicit"]},
         "ply": {"type": "integer", "description": "Only with mode=filter."},
         "style": {"type": "string", "description": "FEFCO code, only with mode=filter."},
         "line_nos": {"type": "array", "items": {"type": "integer"},
                      "description": "Only with mode=explicit."}},
         "required": ["mode"]}},

    {"name": "set_terms",
     "description": "Set payment terms and the cost of capital used to NPV-adjust "
                    "vendors who quote different terms. This decides who looks "
                    "cheapest, so state that when you set it.",
     "input_schema": {"type": "object", "properties": {
         "payment_terms_days": {"type": "integer"},
         "cost_of_capital_pct": {"type": "number"}},
         "required": ["payment_terms_days"]}},

    {"name": "set_questionnaire",
     "description": "Choose which questions vendors must answer, and which of "
                    "those answers are allowed to DISQUALIFY a vendor. Gating is "
                    "buyer policy, not a property of the software.",
     "input_schema": {"type": "object", "properties": {
         "question_nos": {"type": "array", "items": {"type": "integer"}},
         "gating_q_nos": {"type": "array", "items": {"type": "integer"}}},
         "required": ["question_nos"]}},

    {"name": "choose_vendors",
     "description": "Choose which vendors are invited.",
     "input_schema": {"type": "object", "properties": {
         "vendor_ids": {"type": "array", "items": {"type": "string"}}},
         "required": ["vendor_ids"]}},

    {"name": "show_draft",
     "description": "Re-render the RFx as it stands, with what is still missing.",
     "input_schema": {"type": "object", "properties": {}}},

    {"name": "draft_mail",
     "description": "Record the covering mail you have written for the buyer to "
                    "approve. Write it yourself — subject and body — in the "
                    "buyer's voice, naming the response deadline and the format "
                    "they should reply in.",
     "input_schema": {"type": "object", "properties": {
         "subject": {"type": "string"},
         "body": {"type": "string"}},
         "required": ["subject", "body"]}},

    {"name": "issue_rfx",
     "description": "Issue the RFx to the chosen vendors. Only call this once the "
                    "buyer has seen the mail draft and said to send it.",
     "input_schema": {"type": "object", "properties": {}}},
]


class AuthorTools:
    """Applies buyer decisions to a draft. Owns no I/O and runs no pipeline."""

    def __init__(self, draft: RfxDraft, catalogue: dict):
        self.draft = draft
        self.cat = catalogue          # {"lines": [...], "questions": [...], "vendors": [...]}

    # -- dispatch ----------------------------------------------------------
    def dispatch(self, name: str, args: dict):
        fn = getattr(self, f"_{name}", None)
        if fn is None:
            return {"error": f"no such tool: {name}"}, []
        return fn(**args)

    # -- tools -------------------------------------------------------------
    def _list_catalogue(self, kind: str):
        rows = self.cat.get(kind, [])
        return {"kind": kind, "count": len(rows), "items": rows}, []

    def _set_header(self, **kw):
        for k, v in kw.items():
            if v is not None:
                setattr(self.draft, k, v)
        return {"ok": True, "header": kw}, [self._draft_block()]

    def _choose_lines(self, mode: str, ply=None, style=None, line_nos=None):
        lines = self.cat["lines"]
        if mode == "all":
            chosen = [l["line_no"] for l in lines]
        elif mode == "explicit":
            valid = {l["line_no"] for l in lines}
            chosen = [n for n in (line_nos or []) if n in valid]
            unknown = sorted(set(line_nos or []) - valid)
            if unknown:
                return ({"error": f"not in the item master: {unknown}. "
                                  f"Call list_catalogue first."}, [])
        else:
            chosen = [l["line_no"] for l in lines
                      if (ply is None or l.get("ply") == ply)
                      and (style is None or l.get("style") == style)]
        if not chosen:
            return {"error": "that filter matches no lines in the item master."}, []
        self.draft.line_nos = sorted(chosen)
        return ({"chosen": len(chosen), "of": len(lines), "line_nos": self.draft.line_nos},
                [self._draft_block()])

    def _set_terms(self, payment_terms_days: int, cost_of_capital_pct=None):
        self.draft.payment_terms_days = int(payment_terms_days)
        if cost_of_capital_pct is not None:
            self.draft.cost_of_capital_pct = float(cost_of_capital_pct)
        return ({"payment_terms_days": self.draft.payment_terms_days,
                 "cost_of_capital_pct": self.draft.cost_of_capital_pct,
                 "note": "Every rate that comes back will be NPV-adjusted to these "
                         "terms at this cost of capital."},
                [self._draft_block()])

    def _set_questionnaire(self, question_nos: list, gating_q_nos=None):
        valid = {q["q_no"] for q in self.cat["questions"]}
        chosen = [n for n in question_nos if n in valid]
        gates = [n for n in (gating_q_nos or []) if n in chosen]
        if not chosen:
            return {"error": "none of those question numbers exist."}, []
        self.draft.question_nos = sorted(chosen)
        self.draft.gating_q_nos = sorted(gates)
        return ({"questions": self.draft.question_nos, "gating": self.draft.gating_q_nos,
                 "note": "Only the gating questions can disqualify a vendor."},
                [self._draft_block()])

    def _choose_vendors(self, vendor_ids: list):
        valid = {v["vendor_id"] for v in self.cat["vendors"]}
        chosen = [v for v in vendor_ids if v in valid]
        if not chosen:
            return ({"error": f"none of those vendors are on the approved list "
                              f"({sorted(valid)})."}, [])
        self.draft.vendor_ids = chosen
        return {"invited": chosen}, [self._draft_block()]

    def _show_draft(self):
        return {"missing": self.draft.missing()}, [self._draft_block()]

    def _draft_mail(self, subject: str, body: str):
        self.draft.mail_subject = subject
        self.draft.mail_body = body
        names = {v["vendor_id"]: v["name"] for v in self.cat["vendors"]}
        return ({"drafted": True, "missing": self.draft.missing()},
                [MailDraftBlock(
                    to=[names.get(v, v) for v in self.draft.vendor_ids],
                    subject=subject, body=body,
                    attachments=["rfx_line_schedule.xlsx", "quality_questionnaire.pdf"])])

    def _issue_rfx(self):
        gaps = self.draft.missing()
        if gaps:
            return ({"error": f"cannot issue yet — still missing {', '.join(gaps)}."},
                    [self._draft_block()])
        if not self.draft.mail_body:
            return {"error": "draft the covering mail first, so the buyer can approve it."}, []
        # The API layer watches for this and runs the pipeline. See the module
        # docstring for why that job does not live here.
        self.draft.issued = True
        return ({"issued": True, "_run_pipeline": True,
                 "vendors": self.draft.vendor_ids, "lines": len(self.draft.line_nos)},
                [TextBlock(text=f"Issued to {len(self.draft.vendor_ids)} vendors. "
                                f"(The send is stubbed — no mail left the building.) "
                                f"Reading the responses now.")])

    # -- rendering ---------------------------------------------------------
    def _draft_block(self) -> RfxDraftBlock:
        d = self.draft
        q = {x["q_no"]: x["question"] for x in self.cat["questions"]}
        names = {v["vendor_id"]: v["name"] for v in self.cat["vendors"]}
        f = []
        if d.buyer_org:
            f.append(DraftField(label="Buyer", value=d.buyer_org))
        if d.category:
            f.append(DraftField(label="Category", value=d.category))
        if d.delivery_point:
            f.append(DraftField(label="Delivery point", value=d.delivery_point))
        if d.required_incoterm:
            f.append(DraftField(label="Incoterm", value=d.required_incoterm,
                                changes="Vendors quoting a different incoterm get a "
                                        "freight adjustment before comparison"))
        if d.payment_terms_days is not None:
            f.append(DraftField(
                label="Payment terms", value=f"{d.payment_terms_days} days from GRN",
                changes=f"Every rate is NPV-adjusted to this at "
                        f"{d.cost_of_capital_pct or 9.0}% — it decides who looks cheapest"))
        if d.response_due:
            f.append(DraftField(label="Responses due", value=d.response_due))
        return RfxDraftBlock(
            fields=f,
            lines_included=len(d.line_nos), lines_available=len(self.cat["lines"]),
            questions_included=len(d.question_nos),
            gating=[f"Q{n} · {q.get(n, '')}" for n in d.gating_q_nos],
            vendors=[names.get(v, v) for v in d.vendor_ids],
            missing=d.missing(), ready=not d.missing())
