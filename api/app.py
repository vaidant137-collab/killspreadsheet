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

from analyst.author import AUTHOR_SYSTEM, AUTHOR_TOOL_SPECS, AuthorTools
from analyst.loop import Analyst
from analyst.tools import build_comparison
from config import DATA, DB_PATH, REVIEW_THRESHOLD, ROOT
from contracts.rfx import RfxDraft
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


# --- the two halves of the product -----------------------------------------
# "draft": no RFx exists yet; the co-pilot has authoring tools and the screen is
# an empty chat. "comparison": responses are in and the analyst takes over.
#
# One process-wide session, like the rate limiter above, because this is a demo
# on a single free instance. A real deployment keys this per buyer; the shape of
# the code does not change, only where the dict lives.
SESSION = {"phase": "draft", "draft": RfxDraft()}


def _catalogue() -> dict:
    """What the buyer has to choose FROM. Read from the item master, never
    invented — a co-pilot that proposes a line item the buyer does not stock has
    wasted the tender."""
    gt = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))
    return {
        "lines": [{"line_no": l["line_no"], "code": l["code"],
                   "description": l["description"], "style": l["style"],
                   "ply": l.get("ply"), "annual_qty": l["annual_qty"],
                   "uom": l["uom"], "food_contact": l.get("food_contact", False),
                   "requires_tooling": l.get("requires_tooling", False)}
                  for l in gt["rfx"]["lines"]],
        "questions": [{"q_no": q["q_no"], "question": q["question"],
                       "answer_type": q["answer_type"]}
                      for q in gt["rfx"]["questionnaire"]],
        "vendors": [{"vendor_id": s_["vendor"]["vendor_id"], "name": s_["vendor"]["name"],
                     "city": s_["vendor"].get("city"),
                     "incumbent": s_["vendor"].get("is_incumbent", False)}
                    for s_ in gt["submissions"]],
        "defaults": {"buyer_org": gt["rfx"]["buyer_org"],
                     "category": gt["rfx"]["category"],
                     "delivery_point": gt["rfx"]["delivery_point"],
                     "required_incoterm": gt["rfx"]["required_incoterm"],
                     "response_due": gt["rfx"]["response_due"]},
    }


def _issue(draft: RfxDraft) -> None:
    """Run the whole pipeline against the RFx the buyer just authored.

    Lives here rather than in analyst/author.py because this module is a
    composition root and that one is a leaf. A leaf importing `pipeline` would
    quietly invert the dependency the whole architecture rests on.
    """
    import pipeline
    pipeline.run(fresh=True, verbose=False, draft=draft)
    SESSION["phase"] = "comparison"


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
            "provenance": _provenance(), "phase": SESSION["phase"],
            "comparison": json.loads(blocks[0].model_dump_json())}


def _provenance() -> dict:
    """Where the numbers on screen actually came from.

    The one thing a demo must never do is let a viewer assume a model read the
    documents when a fixture did. So this is served to the header, unprompted,
    on every load: the model name and the timestamp of the run, or a plain
    admission that this instance is running the stand-in.
    """
    from extract.recorded import provenance
    runs = (provenance() or {}).get("runs") or []
    if not runs:
        return {"mode": "fixture",
                "label": "fixture path — no model read these documents",
                "detail": "Extraction is replaying known-good output. Deploy with "
                          "an API key set, or run `python -m pipeline "
                          "--extractor record`, to have a model do the reading."}
    models = sorted({r["model"] for r in runs})
    return {"mode": "recorded",
            "label": f"extraction by {', '.join(models)}",
            "detail": f"{len(runs)} documents parsed by a real model run, "
                      f"recorded {min(r['recorded_at'] for r in runs)} and "
                      f"replayed verbatim. Re-recorded on every deploy.",
            "runs": runs}


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


@app.get("/api/doc/{doc_id}/preview")
def doc_preview(doc_id: str, locator: str = "") -> dict:
    """The source document, rendered in place.

    A download is where provenance goes to die: the buyer has to leave the
    screen, find the file, open Excel, work out which sheet, and come back
    having forgotten what they were checking. Serving structured content
    instead keeps the whole loop inside one window.
    """
    from tools.doc_preview import preview
    conn = db()
    r = conn.execute("SELECT path FROM source_doc WHERE doc_id=?", (doc_id,)).fetchone()
    if not r:
        raise HTTPException(404, doc_id)
    p_ = ROOT / r["path"]
    if not p_.exists():
        raise HTTPException(404, str(p_))
    out = preview(p_, locator)
    out["doc_id"] = doc_id
    out["filename"] = p_.name
    return out


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

    # Which agent answers depends on whether an RFx exists yet. Same loop, same
    # Block contract to the screen; different tools and a different brief.
    drafting = SESSION["phase"] == "draft"
    if drafting:
        tools = AuthorTools(SESSION["draft"], _catalogue())
        agent = Analyst(conn, tools=tools, specs=AUTHOR_TOOL_SPECS,
                        system=AUTHOR_SYSTEM)
    else:
        agent = Analyst(conn)

    def stream():
        issued = False
        for kind, payload in agent.ask(a.question):
            body = (payload if isinstance(payload, str)
                    else json.loads(payload.model_dump_json()))
            yield f"data: {json.dumps({'kind': kind, 'payload': body})}\n\n"
            if drafting and SESSION["draft"].issued and not issued:
                issued = True
        if issued:
            # The vendors "reply". Extraction, matching, normalisation and
            # allocation all run now, against the RFx the buyer just wrote.
            yield ("data: " + json.dumps({"kind": "status",
                                          "payload": "reading five responses…"}) + "\n\n")
            try:
                _issue(SESSION["draft"])
                yield "data: " + json.dumps({"kind": "issued"}) + "\n\n"
            except Exception as e:                            # noqa: BLE001
                SESSION["draft"].issued = False
                body = {"type": "refusal", "question": a.question,
                        "reason": f"The RFx went out but reading the responses "
                                  f"failed: {type(e).__name__}: {e}",
                        "would_need": ["The draft is intact — try issuing again."]}
                yield "data: " + json.dumps({"kind": "block", "payload": body}) + "\n\n"
        yield "data: {\"kind\": \"done\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/issue_default")
def issue_default() -> dict:
    """Issue the template RFx, unauthored.

    Demo insurance. Opening on an empty chat is the honest shape of the product,
    but it makes the FIRST thing a visitor sees depend on a live model call. If
    the key is missing, the budget is spent or the provider is down, a reviewer
    would otherwise get a blank box and no way past it — and lose the half of the
    build that does not need a model at all.

    This is not a hidden happy path: it issues the item master as written, and
    the header still reports which extractor produced the numbers.
    """
    cat = _catalogue()
    d = RfxDraft(
        buyer_org=cat["defaults"]["buyer_org"], category=cat["defaults"]["category"],
        delivery_point=cat["defaults"]["delivery_point"],
        required_incoterm=cat["defaults"]["required_incoterm"],
        response_due=cat["defaults"]["response_due"],
        payment_terms_days=45,
        line_nos=[l["line_no"] for l in cat["lines"]],
        question_nos=[q["q_no"] for q in cat["questions"]],
        gating_q_nos=[1, 7],
        vendor_ids=[v["vendor_id"] for v in cat["vendors"]],
        mail_subject="RFX-2026-CORR-011 — annual corrugated requirement FY27",
        mail_body="(template RFx, issued without authoring)")
    SESSION["draft"] = d
    d.issued = True
    _issue(d)
    return {"ok": True, "phase": SESSION["phase"]}


@app.post("/api/reset")
def reset() -> dict:
    """Back to an empty chat and a blank RFx, so the flow can be demonstrated
    twice without a redeploy."""
    SESSION["phase"] = "draft"
    SESSION["draft"] = RfxDraft()
    return {"ok": True, "phase": "draft"}


@app.get("/api/catalogue")
def catalogue() -> dict:
    """The item master, questionnaire and approved vendor list. Served so the
    empty state can show the buyer what there is to choose from rather than
    making them guess at a blank box."""
    return _catalogue()


@app.get("/api/options")
def options() -> dict:
    """The decision layer. Served from the store and the authored RFx, so it
    renders with no model call and cannot disagree with the table above it.

    It rebuilds through the same `apply_draft` the pipeline used rather than
    reconstructing the RFx from the database, because gating is a buyer policy
    that the schema does not persist — reading it back from the template would
    quietly answer a question about a tender nobody issued.
    """
    import json as _json

    import pipeline
    from allocate.subsets import options as build_options
    from contracts.quote import GroundTruth
    from normalize.engine import normalise_all

    gt = GroundTruth.model_validate(
        _json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    draft = SESSION["draft"]
    if draft.issued:
        gt = pipeline.apply_draft(gt, draft)
    return {"cards": build_options(gt, normalise_all(gt)),
            "authored": draft.issued}


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
