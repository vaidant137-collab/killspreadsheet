"""
The server behind the chat.

Chat drives, one canvas mutates, one drawer opens. Everything except the
analyst's own reasoning is served straight from the database, which is why the
comparison, the evidence drawer, the review queue and the assumptions panel all
work with no model API key at all.

Run:  uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from analyst.loop import Analyst
from analyst.tools import build_comparison
from config import DB_PATH, REVIEW_THRESHOLD, ROOT
from store import repo

app = FastAPI(title="Kill the Quote Spreadsheet")
WEB = ROOT / "web"

# --- a ceiling on the public demo ------------------------------------------
# This runs on a public URL with a paid API key behind it. Without a cap, one
# person holding down Enter drains the budget and the demo is dead for whoever
# opens the link next. In-memory is enough: the free tier is a single instance,
# and a counter that resets on redeploy is the right amount of machinery for a
# demo. A real deployment would put this in the store with a per-viewer key.
MAX_PER_HOUR = int(os.getenv("MAX_QUESTIONS_PER_HOUR", "60"))
_asks: list[float] = []


def _within_budget() -> tuple[bool, int]:
    now = time.time()
    _asks[:] = [t for t in _asks if now - t < 3600]
    return len(_asks) < MAX_PER_HOUR, MAX_PER_HOUR - len(_asks)


def db():
    if not DB_PATH.exists():
        raise HTTPException(503, "Database not built. Run `python -m pipeline` first.")
    return repo.connect(DB_PATH)


@app.get("/healthz")
def healthz() -> dict:
    """Hosts poll this to decide the service is alive. Kept free of database
    access so a half-built deploy reports honestly rather than 500-ing."""
    ok, left = _within_budget()
    return {"ok": True, "db": DB_PATH.exists(),
            "questions_left_this_hour": left if ok else 0}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/api/state")
def state() -> dict:
    conn = db()
    rfx = dict(conn.execute("SELECT * FROM rfx LIMIT 1").fetchone())
    vendors = [dict(r) for r in conn.execute(
        "SELECT vendor_id,name,city,reply_format,currency,incoterm,tax_basis,"
        "payment_days,validity_days,moq_pieces,qualified,disqualified_because "
        "FROM vendor ORDER BY name").fetchall()]
    for v in vendors:
        v["disqualified_because"] = json.loads(v["disqualified_because"] or "[]")

    counts = dict(conn.execute(
        "SELECT COUNT(*) AS cells,"
        " SUM(state='unresolved') AS unresolved,"
        " SUM(state='derived') AS derived,"
        " SUM(state='extracted') AS extracted"
        " FROM normalised_line").fetchone())
    open_reviews = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    contradictions = [dict(r) for r in conn.execute(
        "SELECT vendor_id, q_no, answer, contradiction_note FROM questionnaire_answer "
        "WHERE contradicted_by_evidence=1").fetchall()]
    injections = [dict(r) for r in conn.execute(
        "SELECT vendor_id, excerpt FROM injection_attempt").fetchall()]

    _, blocks = build_comparison(conn)
    return {"rfx": rfx, "vendors": vendors, "counts": counts,
            "open_reviews": open_reviews, "threshold": REVIEW_THRESHOLD,
            "contradictions": contradictions, "injections": injections,
            "comparison": json.loads(blocks[0].model_dump_json())}


@app.get("/api/comparison")
def comparison(lines: str | None = None, vendors: str | None = None) -> dict:
    conn = db()
    ln = [int(x) for x in lines.split(",")] if lines else None
    vd = vendors.split(",") if vendors else None
    _, blocks = build_comparison(conn, ln, vd)
    return json.loads(blocks[0].model_dump_json())


@app.get("/api/evidence/{evidence_id}")
def evidence(evidence_id: str) -> dict:
    conn = db()
    r = conn.execute(
        "SELECT e.*, d.path, d.kind, d.vendor_id FROM evidence e "
        "JOIN source_doc d ON d.doc_id=e.doc_id WHERE e.evidence_id=?",
        (evidence_id,)).fetchone()
    if not r:
        raise HTTPException(404, f"no evidence {evidence_id}")
    row = dict(r)
    row["url"] = f"/api/doc/{row['doc_id']}"
    n = conn.execute(
        "SELECT vendor_id,line_no,as_quoted,landed_inr,state,caveats,"
        "assumptions_used,missing_fact,unresolved_reason,extraction_confidence,"
        "match_confidence FROM normalised_line WHERE evidence_id=?",
        (evidence_id,)).fetchone()
    if n:
        row["cell"] = dict(n)
        row["cell"]["caveats"] = json.loads(row["cell"]["caveats"] or "[]")
        row["cell"]["assumptions_used"] = json.loads(row["cell"]["assumptions_used"] or "[]")
        q = conn.execute(
            "SELECT vendor_label, rate, currency, basis, match_confidence, "
            "match_rationale FROM vendor_quote_line WHERE vendor_id=? AND line_no=?",
            (n["vendor_id"], n["line_no"])).fetchone()
        if q:
            row["quote"] = dict(q)
    return row


@app.get("/api/doc/{doc_id}")
def doc(doc_id: str):
    conn = db()
    r = conn.execute("SELECT path FROM source_doc WHERE doc_id=?", (doc_id,)).fetchone()
    if not r:
        raise HTTPException(404, doc_id)
    p = ROOT / r["path"]
    if not p.exists():
        raise HTTPException(404, str(p))
    return FileResponse(p)


@app.get("/api/reviews")
def reviews(limit: int = 30) -> dict:
    conn = db()
    rows = [dict(r) for r in conn.execute(
        "SELECT r.*, n.missing_fact, n.unresolved_reason, q.match_rationale, "
        "q.vendor_label, l.description FROM review_item r "
        "LEFT JOIN normalised_line n ON n.vendor_id=r.vendor_id AND n.line_no=r.line_no "
        "LEFT JOIN vendor_quote_line q ON q.vendor_id=r.vendor_id AND q.line_no=r.line_no "
        "LEFT JOIN rfx_line l ON l.line_no=r.line_no "
        "WHERE r.status='open' ORDER BY r.confidence ASC LIMIT ?", (limit,)).fetchall()]
    total = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    return {"open": total, "items": rows, "threshold": REVIEW_THRESHOLD}


class Decision(BaseModel):
    action: str                      # accept | correct
    value: str | None = None
    reviewer: str = "buyer"


@app.post("/api/review/{review_id}")
def decide(review_id: int, d: Decision) -> dict:
    conn = db()
    if d.action == "accept":
        conn.execute("UPDATE review_item SET status='accepted', reviewer=?, "
                     "reviewed_at=datetime('now') WHERE id=?", (d.reviewer, review_id))
        conn.commit()
    else:
        repo.record_correction(conn, review_id, d.value or "", d.reviewer)
    left = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    return {"ok": True, "open": left}


class Ask(BaseModel):
    question: str


@app.post("/api/ask")
def ask(a: Ask):
    """Server-sent events. Blocks reach the UI as they are produced, so a
    multi-step answer shows its working rather than appearing all at once."""
    conn = db()
    ok, left = _within_budget()
    if not ok:
        def refuse():
            body = {"type": "refusal", "question": a.question,
                    "reason": f"This public demo allows {MAX_PER_HOUR} analyst "
                              f"questions an hour and that is spent. Everything "
                              f"else on the page still works — the comparison, "
                              f"the evidence drawer, the review queue and the "
                              f"assumptions panel are served from the database, "
                              f"not the model.",
                    "would_need": ["Try again in a little while, or run it "
                                   "locally with your own key."]}
            yield f"data: {json.dumps({'kind': 'block', 'payload': body})}\n\n"
            yield "data: {\"kind\": \"done\"}\n\n"
        return StreamingResponse(refuse(), media_type="text/event-stream")
    _asks.append(time.time())

    analyst = Analyst(conn)

    def stream():
        for kind, payload in analyst.ask(a.question):
            body = (payload if isinstance(payload, str)
                    else json.loads(payload.model_dump_json()))
            yield f"data: {json.dumps({'kind': kind, 'payload': body})}\n\n"
        yield "data: {\"kind\": \"done\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/memo")
def memo() -> dict:
    """The decision record. The artifact that actually leaves the tool."""
    conn = db()
    from allocate.subsets import allocate
    from pipeline import load_gt
    from analyst import memo as memo_mod
    gt = load_gt()
    rows = [dict(r) for r in conn.execute("SELECT * FROM normalised_line").fetchall()]
    from contracts.normalized import CellState, NormalisedLine
    from contracts.rfx import Uom
    normalised = [NormalisedLine(
        vendor_id=r["vendor_id"], line_no=r["line_no"], buyer_uom=Uom(r["buyer_uom"]),
        as_quoted=r["as_quoted"], landed_inr=r["landed_inr"],
        state=CellState(r["state"]), freight_inr=r["freight_inr"],
        missing_fact=r["missing_fact"]) for r in rows]
    allocs = [a for a in allocate(gt, normalised) if a.feasible]
    if not allocs:
        raise HTTPException(409, "No feasible split to recommend.")
    return {"markdown": memo_mod.build(conn, allocs[0]), "strategy": allocs[0].strategy}


@app.get("/api/assumptions")
def assumptions() -> dict:
    conn = db()
    return {"rows": [dict(r) for r in conn.execute(
        "SELECT * FROM assumption ORDER BY key").fetchall()]}
