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
    QueryBlock, ReviewBlock, ReviewCard, Series, TableBlock,
)
from store import repo

TOOL_SPECS = [
    {
        "name": "run_sql",
        "description": (
            "Run one read-only SELECT against the comparison database and get rows back. "
            "This is how you obtain every number you report. Never state a figure you "
            "did not get from here.\n\n"
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
               "qty": Cell(value=f"{l['annual_qty']:,}")}
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
    foot = [f"Landed cost per buyer unit, pre-tax, adjusted to the RFx's 45-day terms. "
            f"{unres} cells unresolved — shown as a gap, never as zero."]
    dq = [v["name"] for v in vends if not v["qualified"]]
    if dq:
        foot.append("⚑ did not clear the quality questionnaire: " + ", ".join(dq))

    b = TableBlock(title=title or "Side-by-side comparison — landed ₹ per unit",
                   columns=cols, rows=rows, footnotes=foot, pin=True)
    return {"lines": len(rows), "vendors": len(vends)}, [b]
