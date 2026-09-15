"""
The analyst's tool surface. Five tools, deliberately small.

The rule that governs all of them: **the analyst never does arithmetic.** Every
number in every answer came out of a tool call. A model summing 150 figures in
its head is not analysis, it is a plausible-looking guess, and the moment one
number is wrong none of the others can be trusted either.

`run_sql` is read-only at the tool boundary, not by convention. `compute` runs
in a namespace with no imports, no builtins worth having, and no filesystem.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from contracts.blocks import (
    AssumptionBlock, AssumptionRow, Cell, ChartBlock, Column, EvidenceBlock,
    QueryBlock, RefusalBlock, ReviewBlock, ReviewCard, Series, TableBlock,
)
from contracts.rfx import uom_label
from store import repo

# The typed tools come first deliberately. Free-form SQL against a ten-table
# schema does not usually fail loudly — it returns a wrong-but-valid number,
# which is the worst failure mode available here, because it is indistinguishable
# on screen from a right one. These four cover what buyers actually ask, compute
# in Python, and cannot be subtly wrong about what they exclude.
TOOL_SPECS = [
    {
        "name": "vendor_totals",
        "description": (
            "Total landed cost per vendor across the lines they quoted, with the "
            "coverage that total rests on. Use this for anything of the form 'who "
            "is cheapest overall' or 'what would vendor X cost me'.\n\n"
            "Returns, per vendor: lines_quoted, lines_priced, lines_unresolved, "
            "annual_landed_inr, qualified, and lead_time_days. The totals cover "
            "ONLY priced lines — a vendor with six unresolved lines looks cheap for "
            "a reason, and lines_unresolved is how you say so."),
        "input_schema": {"type": "object", "properties": {
            "qualified_only": {"type": "boolean",
                               "description": "Restrict to vendors who cleared the gate."}}},
    },
    {
        "name": "cheapest_per_line",
        "description": (
            "The cheapest vendor on every line, among the vendors you name (or all "
            "of them). This is the 'cheapest per line' question the VP asks. "
            "Returns each line's winner, their landed rate, the runner-up and the "
            "gap, plus lines nobody priced."),
        "input_schema": {"type": "object", "properties": {
            "vendor_ids": {"type": "array", "items": {"type": "string"},
                           "description": "Omit for all vendors."},
            "qualified_only": {"type": "boolean"}}},
    },
    {
        "name": "best_split",
        "description": (
            "Enumerate every award split and return them ranked, with the "
            "constraints each one violates. Use for 'what if I split it', 'is a "
            "single vendor viable', 'what does that split cost versus one vendor'."),
        "input_schema": {"type": "object", "properties": {
            "max_vendors": {"type": "integer"},
            "qualified_only": {"type": "boolean"}}},
    },
    {
        "name": "show_options",
        "description": (
            "Re-render the three decision cards — cheapest, fastest, single vendor "
            "— with cost, lead time and feasibility. Use when the buyer asks what "
            "their choices are, or after a change that moves them."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_sql",
        "description": (
            "ESCAPE HATCH. Run one read-only SELECT when none of the typed tools above "
            "fits the question. Prefer them: they compute in Python and cannot be "
            "quietly wrong about what they left out. Never state a figure you did "
            "not get from a tool.\n\n"
            "Tables:\n"
            "  rfx_line(line_no, code, description, style, ply, length_mm, width_mm, "
            "height_mm, liner_gsm, gsm_stack, bursting_factor, print_spec, annual_qty, "
            "uom, unit_weight_g, food_contact, requires_tooling, sub_components)\n"
            "  vendor(vendor_id, name, city, incumbent, reply_format, currency, incoterm, "
            "tax_basis, payment_days, validity_days, moq_pieces, qualified, "
            "disqualified_because)\n"
            "  normalised_line(vendor_id, line_no, buyer_uom, as_quoted, landed_inr, "
            "state, unresolved_reason, missing_fact, assumptions_used, caveats, "
            "base_inr, freight_inr, tooling_inr, discount_inr, npv_adjustment_inr, "
            "evidence_id, extraction_confidence, match_confidence)\n"
            "  vendor_quote_line(vendor_id, line_no, vendor_label, rate, currency, basis, "
            "match_confidence, match_rationale, evidence_id)\n"
            "  questionnaire_answer(vendor_id, q_no, question, answer, evidence_id, "
            "contradicted_by_evidence, contradiction_note)\n"
            "  review_item(id, vendor_id, line_no, field, proposed_value, confidence, status)\n"
            "  assumption(key, label, value, unit, source)\n"
            "  evidence(evidence_id, doc_id, locator, snippet, page, bbox)\n"
            "  source_doc(doc_id, vendor_id, path, kind, role)\n"
            "  injection_attempt(vendor_id, excerpt)\n\n"
            "normalised_line.state is 'extracted' | 'derived' | 'unresolved'. An "
            "unresolved row has landed_inr = NULL and is NOT zero — never let it fall "
            "silently out of a SUM or an average without saying so."
        ),
        "input_schema": {"type": "object", "properties": {
            "sql": {"type": "string"},
            "purpose": {"type": "string",
                        "description": "One line: what this query is for."}},
            "required": ["sql", "purpose"]},
    },
    {
        "name": "compute",
        "description": (
            "Evaluate a short Python expression or small script over rows you already "
            "fetched, for anything SQL is awkward at — NPV, slab re-costing, split "
            "comparison. Assign the result to `result`. `rows` holds the last query's "
            "output. No imports, no filesystem."),
        "input_schema": {"type": "object", "properties": {
            "code": {"type": "string"},
            "purpose": {"type": "string"}}, "required": ["code", "purpose"]},
    },
    {
        "name": "chart",
        "description": (
            "Draw a chart from rows you fetched. Pass the category labels and one or "
            "more series of numbers. Do not invent values — every number here must "
            "have come from run_sql or compute."),
        "input_schema": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["bar", "line", "grouped_bar"]},
            "title": {"type": "string"},
            "categories": {"type": "array", "items": {"type": "string"}},
            "series": {"type": "array", "items": {"type": "object", "properties": {
                "label": {"type": "string"},
                "values": {"type": "array", "items": {"type": "number"}}},
                "required": ["label", "values"]}},
            "unit": {"type": "string"}},
            "required": ["title", "categories", "series"]},
    },
    {
        "name": "get_evidence",
        "description": (
            "Open the source behind a specific extracted value: the PDF page, the "
            "workbook cell, or the cropped region of the photograph. Use it whenever "
            "the buyer asks why a number is what it is."),
        "input_schema": {"type": "object", "properties": {
            "evidence_id": {"type": "string"},
            "caption": {"type": "string"}}, "required": ["evidence_id"]},
    },
    {
        "name": "show_comparison",
        "description": (
            "Render or update the pinned side-by-side comparison. Give the buyer line "
            "numbers to show and optionally the vendors to include. This MUTATES the "
            "pinned table rather than printing a new copy into the conversation."),
        "input_schema": {"type": "object", "properties": {
            "line_nos": {"type": "array", "items": {"type": "integer"}},
            "vendor_ids": {"type": "array", "items": {"type": "string"}},
            "title": {"type": "string"}}, "required": []},
    },
    {
        "name": "show_review_queue",
        "description": (
            "Show cells the extractor was not confident about, so a human can accept "
            "or correct them. Use this when asked where the system is unsure."),
        "input_schema": {"type": "object", "properties": {
            "limit": {"type": "integer"}}, "required": []},
    },
    {
        "name": "refuse",
        "description": (
            "The data cannot answer this question. Say so and name what you would "
            "need. Use this INSTEAD of writing an apology in prose: it renders as "
            "its own block with the missing facts listed, and a refusal that names "
            "the gap is what makes every other answer worth trusting.\n\n"
            "Reach for it whenever the question asks about something an RFx does "
            "not contain — reliability, delivery history, OTIF, quality over time, "
            "financial standing, anything about how a vendor has BEHAVED rather "
            "than what they quoted."),
        "input_schema": {"type": "object", "properties": {
            "reason": {"type": "string", "description":
                       "One or two sentences. What this dataset does not contain. "
                       "No apology, no hedging, no offer to do something else."},
            "would_need": {"type": "array", "items": {"type": "string"},
                           "description":
                           "Three to five items, each a fact or dataset you would "
                           "need. Short noun phrases, not sentences, and each one "
                           "named once."}},
            "required": ["reason", "would_need"]},
    },
    {
        "name": "show_assumptions",
        "description": (
            "Show the assumptions every derived number rests on — FX rate, cost of "
            "capital, freight allocation. The buyer can change any of them."),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


class Tools:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.last_rows: list[dict[str, Any]] = []

    # -- typed tools ---------------------------------------------------------
    # Each one owns its own arithmetic and its own exclusions. The point is not
    # that SQL is dangerous; it is that a model writing SQL fails by returning a
    # number that is wrong in a way nothing on screen can show.

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        """Direct read for the typed tools.

        `repo.query` is the guard around MODEL-authored SQL: it refuses writes,
        rejects multiple statements and pins a LIMIT on. None of that applies to
        the queries in this file, which are code and need complete result sets —
        a silently LIMITed total is exactly the wrong-but-plausible number these
        tools exist to prevent.
        """
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _gt(self):
        import json as _json

        from config import DATA
        from contracts.quote import GroundTruth
        gt = GroundTruth.model_validate(
            _json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
        live_l = {r["line_no"] for r in self._q("SELECT line_no FROM rfx_line")}
        live_v = {r["vendor_id"] for r in self._q("SELECT vendor_id FROM vendor")}
        gt.rfx.lines = [l for l in gt.rfx.lines if l.line_no in live_l]
        gt.submissions = [x for x in gt.submissions if x.vendor.vendor_id in live_v]
        for x in gt.submissions:
            x.line_quotes = [q for q in x.line_quotes if q.line_no in live_l]
        return gt

    def vendor_totals(self, qualified_only: bool = False) -> tuple[dict, list]:
        from allocate.subsets import lead_times
        lt = lead_times(self._gt())
        rows = self._q("""
            SELECT v.vendor_id, v.name, v.qualified,
                   COUNT(n.line_no)                                   AS lines_quoted,
                   SUM(n.state != 'unresolved')                       AS lines_priced,
                   SUM(n.state = 'unresolved')                        AS lines_unresolved,
                   SUM(CASE WHEN n.state != 'unresolved'
                            THEN n.landed_inr * l.annual_qty END)     AS annual_landed_inr
            FROM vendor v
            JOIN normalised_line n ON n.vendor_id = v.vendor_id
            JOIN rfx_line l        ON l.line_no  = n.line_no
            GROUP BY v.vendor_id ORDER BY annual_landed_inr""")
        for r in rows:
            r["lead_time_days"] = lt.get(r["vendor_id"])
        if qualified_only:
            rows = [r for r in rows if r["qualified"]]
        self.last_rows = rows
        return ({"vendors": rows,
                 "warning": "Totals cover priced lines only. A vendor with "
                            "unresolved lines is cheap partly because those lines "
                            "are missing — say so alongside the number."},
                [QueryBlock(sql="vendor_totals()", row_count=len(rows))])

    def cheapest_per_line(self, vendor_ids: list | None = None,
                          qualified_only: bool = False) -> tuple[dict, list]:
        where, args = [], []
        if qualified_only:
            where.append("v.qualified = 1")
        if vendor_ids:
            where.append("n.vendor_id IN (%s)" % ",".join("?" * len(vendor_ids)))
            args += list(vendor_ids)
        clause = ("AND " + " AND ".join(where)) if where else ""
        rows = self._q(f"""
            SELECT n.line_no, n.vendor_id, n.landed_inr, l.description, l.annual_qty
            FROM normalised_line n
            JOIN vendor v ON v.vendor_id = n.vendor_id
            JOIN rfx_line l ON l.line_no = n.line_no
            WHERE n.state != 'unresolved' AND n.landed_inr IS NOT NULL {clause}
            ORDER BY n.line_no, n.landed_inr""", tuple(args))
        by_line: dict[int, list] = {}
        for r in rows:
            by_line.setdefault(r["line_no"], []).append(r)
        out = []
        for ln in sorted(by_line):
            bids = by_line[ln]
            w, up = bids[0], (bids[1] if len(bids) > 1 else None)
            out.append({"line_no": ln, "description": w["description"],
                        "annual_qty": w["annual_qty"],
                        "winner": w["vendor_id"], "landed_inr": w["landed_inr"],
                        "runner_up": up["vendor_id"] if up else None,
                        "gap_inr": round(up["landed_inr"] - w["landed_inr"], 4) if up else None,
                        "bidders": len(bids)})
        all_lines = {r["line_no"] for r in self._q("SELECT line_no FROM rfx_line")}
        unpriced = sorted(all_lines - set(by_line))
        self.last_rows = out
        return ({"lines": out, "lines_with_no_price": unpriced,
                 "annual_total_inr": round(
                     sum(r["landed_inr"] * r["annual_qty"] for r in out), 2)},
                [QueryBlock(sql="cheapest_per_line()", row_count=len(out))])

    def best_split(self, max_vendors: int = 3,
                   qualified_only: bool = True) -> tuple[dict, list]:
        from allocate.subsets import allocate, lead_times
        from normalize.engine import normalise_all
        gt = self._gt()
        lt = lead_times(gt)
        allocs = allocate(gt, normalise_all(gt), qualified_only=qualified_only,
                          max_vendors=max_vendors)
        rows = [{"strategy": a.strategy, "vendors": a.vendors_used,
                 "total_inr": round(a.total_inr, 2),
                 "freight_inr": round(a.freight_inr, 2),
                 "tooling_inr": round(a.tooling_inr, 2),
                 "lines_covered": sum(1 for x in a.awards if x.vendor_id),
                 "lead_time_days": (max((lt[v] for v in a.vendors_used), default=None)
                                    if all(lt.get(v) is not None for v in a.vendors_used)
                                    else None),
                 "feasible": a.feasible, "violations": a.violations}
                for a in allocs]
        self.last_rows = rows
        return ({"splits": rows[:12], "evaluated": len(rows)},
                [QueryBlock(sql=f"best_split(max_vendors={max_vendors})",
                            row_count=len(rows))])

    def show_options(self) -> tuple[dict, list]:
        from allocate.subsets import options as build_options
        from contracts.blocks import OptionCard, OptionsBlock
        from normalize.engine import normalise_all
        gt = self._gt()
        cards = build_options(gt, normalise_all(gt))
        return ({"cards": cards},
                [OptionsBlock(cards=[OptionCard(**c) for c in cards])])

    # -- run_sql -------------------------------------------------------------
    def run_sql(self, sql: str, purpose: str = "") -> tuple[dict, list]:
        rows = repo.query(self.conn, sql)
        self.last_rows = rows
        blocks = [QueryBlock(sql=sql.strip(), row_count=len(rows))]
        return {"rows": rows[:80], "row_count": len(rows)}, blocks

    # -- compute -------------------------------------------------------------
    def compute(self, code: str, purpose: str = "") -> tuple[dict, list]:
        safe = {"__builtins__": {
            "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
            "round": round, "sorted": sorted, "range": range, "enumerate": enumerate,
            "zip": zip, "float": float, "int": int, "str": str, "dict": dict,
            "list": list, "set": set, "tuple": tuple, "any": any, "all": all}}
        env = {"rows": self.last_rows, "math": math, "result": None}
        try:
            exec(code, safe, env)                      # noqa: S102 - sandboxed above
        except Exception as e:                          # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}, []
        return {"result": env.get("result")}, [QueryBlock(code=code.strip(),
                                                          row_count=len(self.last_rows))]

    # -- chart ---------------------------------------------------------------
    def chart(self, title, categories, series, kind="bar", unit="INR"):
        b = ChartBlock(kind=kind, title=title, categories=categories, unit=unit,
                       series=[Series(**s) for s in series])
        return {"ok": True}, [b]

    # -- get_evidence --------------------------------------------------------
    def get_evidence(self, evidence_id: str, caption: str = "") -> tuple[dict, list]:
        r = self.conn.execute(
            "SELECT e.*, d.path, d.kind FROM evidence e "
            "JOIN source_doc d ON d.doc_id = e.doc_id WHERE e.evidence_id = ?",
            (evidence_id,)).fetchone()
        if not r:
            return {"error": f"no evidence with id {evidence_id}"}, []
        b = EvidenceBlock(evidence_id=evidence_id, doc_id=r["doc_id"],
                          locator=r["locator"], snippet=r["snippet"],
                          caption=caption or f"{r['doc_id']} · {r['locator']}")
        return {"doc": r["doc_id"], "locator": r["locator"], "kind": r["kind"]}, [b]

    # -- show_comparison -----------------------------------------------------
    def show_comparison(self, line_nos=None, vendor_ids=None, title=None):
        return build_comparison(self.conn, line_nos, vendor_ids, title)

    # -- show_review_queue ---------------------------------------------------
    def show_review_queue(self, limit: int = 8) -> tuple[dict, list]:
        rows = self.conn.execute(
            "SELECT r.*, n.unresolved_reason, n.missing_fact, q.match_rationale "
            "FROM review_item r "
            "LEFT JOIN normalised_line n ON n.vendor_id=r.vendor_id AND n.line_no=r.line_no "
            "LEFT JOIN vendor_quote_line q ON q.vendor_id=r.vendor_id AND q.line_no=r.line_no "
            "WHERE r.status='open' ORDER BY r.confidence ASC LIMIT ?", (limit,)).fetchall()
        total = self.conn.execute(
            "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
        cards = [ReviewCard(
            review_id=r["id"], vendor_id=r["vendor_id"], line_no=r["line_no"],
            field=r["field"], proposed_value=r["proposed_value"],
            confidence=r["confidence"], evidence_id=r["evidence_id"],
            reason=r["missing_fact"] or r["match_rationale"] or r["unresolved_reason"])
            for r in rows]
        b = ReviewBlock(title=f"{total} cells below the confidence threshold",
                        cards=cards, remaining=max(0, total - len(cards)))
        return {"open": total, "shown": len(cards)}, [b]

    # -- show_assumptions ----------------------------------------------------
    def show_assumptions(self) -> tuple[dict, list]:
        rows = self.conn.execute("SELECT * FROM assumption ORDER BY key").fetchall()
        b = AssumptionBlock(
            rows=[AssumptionRow(key=r["key"], label=r["label"], value=r["value"],
                                unit=r["unit"], source=r["source"],
                                editable=bool(r["editable"])) for r in rows],
            note="Change any of these and every derived number recomputes.")
        return {"count": len(rows)}, [b]

    def refuse(self, reason: str, would_need: list[str] | None = None
               ) -> tuple[dict, list]:
        """A refusal is an answer, and it deserves the same treatment as one.

        Written in prose it comes out as an apology with the missing facts
        listed twice and an offer to do something else instead — which is what
        the live site produced when asked which vendor was most reliable. As a
        block it is four lines and unmistakable.
        """
        b = RefusalBlock(question="", reason=reason.strip(),
                         would_need=[w.strip() for w in (would_need or []) if w.strip()])
        return ({"refused": True,
                 "note": "On screen. Do not restate it or offer alternatives."},
                [b])

    def dispatch(self, name: str, args: dict):
        fn = getattr(self, name, None)
        if fn is None:
            return {"error": f"no such tool: {name}"}, []
        return fn(**args)


# ---------------------------------------------------------------------------

def build_comparison(conn, line_nos=None, vendor_ids=None, title=None):
    """The pinned artifact. Renders once, mutates in place thereafter."""
    vends = [dict(r) for r in conn.execute(
        "SELECT vendor_id, name, qualified FROM vendor ORDER BY name").fetchall()]
    if vendor_ids:
        vends = [v for v in vends if v["vendor_id"] in vendor_ids]

    where, params = "", []
    if line_nos:
        where = f" WHERE line_no IN ({','.join('?' * len(line_nos))})"
        params = list(line_nos)
    lines = [dict(r) for r in conn.execute(
        f"SELECT line_no, code, description, uom, annual_qty FROM rfx_line{where} "
        f"ORDER BY line_no", params).fetchall()]

    nl = {(r["vendor_id"], r["line_no"]): dict(r) for r in conn.execute(
        "SELECT * FROM normalised_line").fetchall()}

    cols = [Column(key="line", label="#"), Column(key="item", label="Item"),
            Column(key="qty", label="Annual qty", align="right", numeric=True)]
    for v in vends:
        cols.append(Column(key=v["vendor_id"],
                           label=v["name"].split()[0] + ("" if v["qualified"] else " ⚑"),
                           align="right", numeric=True))

    rows = []
    for l in lines:
        row = {"line": Cell(value=l["line_no"]),
               "item": Cell(value=l["description"][:72], note=l["code"]),
               # Same reason as the memo: the unit belongs on the row. These
               # thirty lines are priced in pieces, kilograms, sets and hundreds
               # of pieces, and the vendor columns are all "landed rupees per
               # ONE OF THESE".
               "qty": Cell(value=f"{l['annual_qty']:,}", note=uom_label(l["uom"]))}
        for v in vends:
            n = nl.get((v["vendor_id"], l["line_no"]))
            if not n:
                row[v["vendor_id"]] = Cell(value="—", state="plain", note="no quote")
                continue
            if n["state"] == "unresolved":
                row[v["vendor_id"]] = Cell(
                    value="—", state="unresolved", note=n["missing_fact"],
                    evidence_id=n["evidence_id"])
            else:
                caveats = json.loads(n["caveats"] or "[]")
                row[v["vendor_id"]] = Cell(
                    value=round(n["landed_inr"], 2), state=n["state"],
                    evidence_id=n["evidence_id"],
                    confidence=round(min(n["extraction_confidence"],
                                         n["match_confidence"]), 2),
                    note=" · ".join(caveats) if caveats else n["as_quoted"])
        rows.append(row)

    unres = sum(1 for r in rows for k, c in r.items() if c.state == "unresolved")
    # Read the terms rather than hard-coding them: the buyer sets them when they
    # author the RFx, and a footnote that says 45 days under a 30-day tender is
    # worse than no footnote.
    terms = conn.execute(
        "SELECT required_payment_terms FROM rfx LIMIT 1").fetchone()["required_payment_terms"]
    foot = [f"Landed cost per buyer unit, pre-tax, adjusted to the RFx's {terms}. "
            f"{unres} cells unresolved — shown as a gap, never as zero."]
    dq = [v["name"] for v in vends if not v["qualified"]]
    if dq:
        foot.append("⚑ did not clear the quality questionnaire: " + ", ".join(dq))

    b = TableBlock(title=title or "Side-by-side comparison — landed ₹ per unit",
                   columns=cols, rows=rows, footnotes=foot, pin=True)
    return {"lines": len(rows), "vendors": len(vends)}, [b]
