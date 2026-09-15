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

from contracts.blocks import (ChoiceBlock, ChoiceOption, DraftField,
                             MailDraftBlock, RfxDraftBlock, TextBlock)
from contracts.rfx import RfxDraft

AUTHOR_SYSTEM = """You are an RFx co-pilot for a category buyer putting roughly \
INR 11 crore of packaging out to tender. They have run tenders before. Your job \
is to hand them a finished draft and make them decide only the things that \
change the outcome.

PROPOSE THE WHOLE THING FIRST. On the buyer's first message, call \
propose_default_rfx. It drafts the complete RFx from their last tender — lines, \
vendors, terms, gates, response date — in one call. Do NOT ask for the buyer's \
organisation, the category, or anything else already on file. A co-pilot that \
interviews the buyer field by field has made them do the data entry.

THEN OFFER CHOICES, NOT QUESTIONS. Anything worth changing goes through \
ask_choice: options they click, one short line each on what that option COSTS. \
Never ask an open question in prose when a choice would do. Never list options \
in a sentence.

ONE DECISION PER TURN, THEN STOP. Call ask_choice at most once and end the \
turn there — no closing sentence, no second picker, no "and also". The buyer \
answers, and the next decision is the next turn's job. Four questions at once \
is the same as none. After propose_default_rfx the decision worth asking first \
is payment terms, because it re-prices every line.

THE CARD IS ON SCREEN. It shows lines, vendors, terms, gates and what is still \
missing. Never restate it, never re-count it, never tell them how many lines or \
vendors they have. They can see it.

NO EXPLANATIONS UNLESS ASKED. Not why payment terms matter, not what NPV is, \
not what a gate does in general. If a choice has a consequence, ask_choice \
carries it on the option itself. One sentence per turn is usually right; three \
is too many.

THE FOUR THINGS THAT DECIDE THE ANSWER are the line schedule, payment terms, \
the vendor list, and which questionnaire answers disqualify. Spend the \
conversation there and nowhere else.

WHEN THEY ARE READY, draft_mail writes the covering note and issue_rfx sends it. \
Say plainly that the send is stubbed."""


# ---------------------------------------------------------------------------
# Tool specs. Deliberately narrow: each one sets a named part of the draft, so
# a wrong call is visible as a wrong field rather than a silently wrong RFx.
# ---------------------------------------------------------------------------

AUTHOR_TOOL_SPECS = [
    {"name": "propose_default_rfx",
     "description": (
         "Draft the WHOLE RFx in one call, from the buyer's last tender: every "
         "line in the category, the approved vendor list, the terms and gates "
         "they used last year, and a response date. Call this FIRST, on the "
         "buyer's opening message, before asking them anything. They can change "
         "any of it afterwards."),
     "input_schema": {"type": "object", "properties": {
         "response_due_days": {"type": "integer",
                               "description": "Days from today. Default 14."}}}},

    {"name": "ask_choice",
     "description": (
         "Put a decision in front of the buyer as options they click. You name "
         "WHAT is being decided; the options and their consequences are computed "
         "from live data — you do not write them and must not invent them.\n\n"
         "  payment_terms  30/45/60/90 days, each with what it moves\n"
         "  gates          each questionnaire question, with who it disqualifies\n"
         "  vendors        the approved list, with who is already invited\n"
         "  lines          the item master by category\n\n"
         "Use this instead of asking an open question in prose. ONCE per turn: "
         "the picker goes on screen and your turn is over. A second call in the "
         "same turn is refused."),
     "input_schema": {"type": "object", "properties": {
         "key": {"type": "string",
                 "enum": ["payment_terms", "gates", "vendors", "lines"]},
         "title": {"type": "string",
                   "description": "Short imperative, e.g. 'Payment terms' or "
                                  "'Gate on'. No question mark, no sentence."}},
         "required": ["key"]}},

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
        # One instance per request, so this is per TURN: which decision has
        # already been put to the buyer and is still waiting for an answer.
        self._asked: list[str] = []

    # -- dispatch ----------------------------------------------------------
    def dispatch(self, name: str, args: dict):
        fn = getattr(self, f"_{name}", None)
        if fn is None:
            return {"error": f"no such tool: {name}"}, []
        return fn(**args)

    # -- tools -------------------------------------------------------------
    def _propose_default_rfx(self, response_due_days: int = 14):
        from datetime import date, timedelta
        d, cat = self.draft, self.cat
        # Called once, at the start. On the live site it was called again on
        # every follow-up — "Payment terms: 30 days" re-proposed the entire RFx
        # before setting them — which costs a turn, re-renders the card for no
        # reason, and moved the response date every time the buyer said anything.
        if d.line_nos:
            return ({"already_drafted": True,
                     "note": "The draft exists and is on screen. Do not call this "
                             "again. Change fields with set_terms, choose_lines, "
                             "choose_vendors or set_questionnaire."}, [])
        dflt = cat.get("defaults", {})
        d.buyer_org = d.buyer_org or dflt.get("buyer_org")
        d.category = d.category or dflt.get("category")
        d.delivery_point = d.delivery_point or dflt.get("delivery_point")
        d.required_incoterm = d.required_incoterm or dflt.get("required_incoterm")
        d.response_due = d.response_due or (
            date.today() + timedelta(days=response_due_days)).isoformat()
        d.line_nos = [l["line_no"] for l in cat["lines"]]
        d.vendor_ids = [v["vendor_id"] for v in cat["vendors"]]
        d.question_nos = [q["q_no"] for q in cat["questions"]]
        d.gating_q_nos = [g["q_no"] for g in cat.get("gate_preview", []) if g["gating_now"]]
        d.payment_terms_days = d.payment_terms_days or 45
        d.cost_of_capital_pct = d.cost_of_capital_pct or 9.0
        return ({"drafted": True, "lines": len(d.line_nos),
                 "vendors": len(d.vendor_ids), "gates": d.gating_q_nos,
                 "note": "A complete RFx, drafted from the buyer's last tender. "
                         "Do not describe it — the card is on screen.",
                 # Naming the next step as DATA, because a model follows a tool
                 # result far more reliably than a line in a system prompt. Terms
                 # first: they NPV-adjust every rate, so they partly decide the
                 # winner, and the vendor list and line schedule are already
                 # right by default and worth nobody's turn.
                 "next_decision": "payment_terms",
                 "why": "It re-prices all 139 cells. Call ask_choice with "
                        "key='payment_terms' and then stop."},
                [self._draft_block()])

    def _ask_choice(self, key: str, title: str = ""):
        """The model names the decision; the options are built from live data.

        Deliberately the model does NOT supply options or consequences. "Gating
        on FSC removes three of five vendors" is a measurement, and a model
        writing that line from memory would produce a number the buyer would act
        on and nobody could check.

        ONE decision per turn. The loop stops the turn the moment a choice
        reaches the screen, and this is the other half of the same guard: a
        single assistant turn can emit several tool calls at once, and the live
        site emitted four identical payment-terms pickers that way. A buyer
        asked four questions at once has been asked none of them.
        """
        builder = getattr(self, f"_choices_{key}", None)
        if builder is None:
            return {"error": f"no choices for '{key}'"}, []
        if self._asked:
            return ({"refused": "one decision at a time",
                     "already_asked": self._asked[0],
                     "note": f"'{self._asked[0]}' is already on screen and the "
                             f"buyer has not answered it. Stop here. Say nothing "
                             f"further this turn."}, [])
        self._asked.append(key)
        block = builder(title)
        return ({"asked": key, "options": [o.label for o in block.options],
                 "note": "The picker is on screen. The turn is over — do not "
                         "describe it, do not ask anything else."}, [block])

    def _choices_payment_terms(self, title: str) -> ChoiceBlock:
        cur = self.draft.payment_terms_days
        return ChoiceBlock(
            key="payment_terms", title=title or "Payment terms",
            other_hint="e.g. 75 days",
            options=[ChoiceOption(value=str(t["days"]),
                                  label=f"{t['days']} days from GRN",
                                  consequence=t.get("consequence"),
                                  selected=(t["days"] == cur))
                     for t in self.cat.get("terms_preview", [])])

    def _choices_gates(self, title: str) -> ChoiceBlock:
        on = set(self.draft.gating_q_nos)
        return ChoiceBlock(
            key="gates", title=title or "Disqualify a vendor for", multi=True,
            allow_other=False,
            options=[ChoiceOption(value=str(g["q_no"]),
                                  label=f"Q{g['q_no']} · {g['question']}",
                                  consequence=g.get("consequence"),
                                  selected=(g["q_no"] in on))
                     for g in self.cat.get("gate_preview", [])])

    def _choices_vendors(self, title: str) -> ChoiceBlock:
        on = set(self.draft.vendor_ids)
        return ChoiceBlock(
            key="vendors", title=title or "Invite", multi=True, allow_other=False,
            options=[ChoiceOption(
                value=v["vendor_id"], label=v["name"],
                consequence=(("incumbent · " if v.get("incumbent") else "")
                             + (v.get("city") or "")),
                selected=(v["vendor_id"] in on)) for v in self.cat["vendors"]])

    def _choices_lines(self, title: str) -> ChoiceBlock:
        n = len(self.cat["lines"])
        chosen = len(self.draft.line_nos)
        return ChoiceBlock(
            key="lines", title=title or "Line schedule", other_hint="e.g. 5-ply only",
            options=[
                ChoiceOption(value="all", label=f"All {n} lines",
                             consequence="the full annual requirement",
                             selected=(chosen == n)),
                ChoiceOption(value="3", label="3-ply only",
                             consequence="the high-volume boxes"),
                ChoiceOption(value="5", label="5-ply only",
                             consequence="the heavier cases"),
                ChoiceOption(value="pick", label="Pick them myself",
                             consequence="opens the item master")])

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
                         "terms at this cost of capital. The card is on screen.",
                 "next_decision": "gates",
                 "why": "Which questionnaire answers disqualify is buyer policy, "
                        "it is the other field that changes who can win, and the "
                        "options carry who each gate would remove. Call ask_choice "
                        "with key='gates' and then stop."},
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
                 "note": "Only the gating questions can disqualify a vendor. The "
                         "card is on screen.",
                 "next_decision": "issue",
                 "why": "Lines and vendors are already right by default and are "
                        "worth nobody's turn. Say the RFx is ready and offer to "
                        "send it; draft_mail when they agree."},
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
