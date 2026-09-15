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
import queue
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from analyst.author import AUTHOR_SYSTEM, AUTHOR_TOOL_SPECS, AuthorTools
from analyst.loop import Analyst
from analyst.tools import build_comparison
from config import DATA, DB_PATH, REVIEW_THRESHOLD, ROOT
from contracts.rfx import RfxDraft, uom_label
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


# --- one session per visitor -------------------------------------------------
# "draft": no RFx exists yet; the co-pilot has authoring tools and the screen is
# an empty chat. "comparison": responses are in and the analyst takes over.
#
# This was one process-wide dict, which is fine until two people open the link.
# The second one arrived into the first one's half-written tender, and anybody
# opening the URL cold landed in the middle of a session they had not started —
# which for a demo link that gets shared is the difference between a product and
# an embarrassment.
#
# So: a cookie, a session per browser, and a DATABASE per session, because
# issuing an RFx rebuilds the store and two buyers issuing different schedules
# would otherwise overwrite each other's comparison. SESSION stays a dict-shaped
# name resolved per request, so every call site below is unchanged.
_SESSIONS: dict[str, dict] = {}
_SESSION_ORDER: list[str] = []
_CURRENT_SID: ContextVar[str] = ContextVar("ks_sid", default="local")
SID_COOKIE = "ks_sid"
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "40"))


def _new_session(sid: str) -> dict:
    return {"phase": "draft", "draft": RfxDraft(),
            "round": {"state": "idle", "vendors": []},
            "db": DATA / "sessions" / f"{sid}.db"}


def _session() -> dict:
    sid = _CURRENT_SID.get()
    s = _SESSIONS.get(sid)
    if s is None:
        s = _SESSIONS[sid] = _new_session(sid)
        _SESSION_ORDER.append(sid)
        # A free instance has a small disk. Keep the newest few and delete the
        # rest, oldest first — a demo nobody has touched in an hour is not worth
        # a megabyte.
        while len(_SESSION_ORDER) > MAX_SESSIONS:
            old = _SESSION_ORDER.pop(0)
            dead = _SESSIONS.pop(old, None)
            if dead and isinstance(dead.get("db"), Path):
                dead["db"].unlink(missing_ok=True)
    return s


class _SessionView:
    """Dict-shaped access to whichever session this request belongs to."""

    def __getitem__(self, k):
        return _session()[k]

    def __setitem__(self, k, v):
        _session()[k] = v

    def get(self, k, default=None):
        return _session().get(k, default)


SESSION = _SessionView()


def _catalogue() -> dict:
    """What the buyer has to choose FROM. Read from the item master, never
    invented — a co-pilot that proposes a line item the buyer does not stock has
    wasted the tender."""
    gt = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))
    return {
        # A real item master has many categories and most of them are somebody
        # else's problem. Showing corrugated alongside four empty ones says this
        # is one category in a buyer's catalogue rather than a demo with the
        # answer hardcoded — and the empty ones say "no data" instead of
        # pretending to have some.
        "categories": [
            {"key": "corrugated", "name": "Corrugated packaging",
             "lines": len(gt["rfx"]["lines"]), "note": None},
            {"key": "flexible", "name": "Flexible packaging", "lines": 0,
             "note": "No data available — not yet loaded into the item master"},
            {"key": "labels", "name": "Labels & tags", "lines": 0,
             "note": "No data available — managed by the marketing category"},
            {"key": "pallets", "name": "Pallets & dunnage", "lines": 0,
             "note": "No data available — on a separate contract to FY28"},
            {"key": "tapes", "name": "Tapes & adhesives", "lines": 0,
             "note": "No data available"},
        ],
        "lines": [{"line_no": l["line_no"], "code": l["code"],
                   "category": "corrugated",
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
        # Consequences are computed HERE, in the composition root, and handed to
        # the co-pilot as data. analyst/author.py must not import allocate/ —
        # and more importantly, a consequence the model wrote from memory would
        # be worse than no consequence at all.
        "gate_preview": _gate_preview(),
        "terms_preview": _terms_preview(),
        "defaults": {"buyer_org": gt["rfx"]["buyer_org"],
                     "category": gt["rfx"]["category"],
                     "delivery_point": gt["rfx"]["delivery_point"],
                     "required_incoterm": gt["rfx"]["required_incoterm"],
                     "response_due": gt["rfx"]["response_due"]},
    }


def _live_gt():
    import json as _json

    from contracts.quote import GroundTruth
    return GroundTruth.model_validate(
        _json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))


def _gate_preview(known_before_quotes: bool = True) -> list[dict]:
    """What gating a question means.

    Before the RFx goes out, that is the SHAPE of the rule and not who it would
    remove: who it removes is in answers nobody has sent yet. The draft-time
    pickers were showing "removes Nova" — read out of Nova's reply, in a
    conversation whose entire premise is that Nova has not replied.
    """
    from allocate.subsets import gate_preview, gate_preview_prior
    gt = _live_gt()
    return gate_preview_prior(gt) if known_before_quotes else gate_preview(gt)


def _terms_preview(known_before_quotes: bool = True) -> list[dict]:
    """What payment terms cost.

    Same rule. Before quotes exist this is the BUYER's working capital on last
    year's awarded spend — knowable, checkable against the FY26 contract, and
    the actual reason the field matters. "Shakti saves you INR 445,474" is a
    number from the future; it tells the buyer what to ask for by reading the
    answers, which is the failure this whole project is an argument against.
    """
    from allocate.subsets import terms_preview, terms_preview_prior
    gt = _live_gt()
    return terms_preview_prior(gt) if known_before_quotes else terms_preview(gt)


@app.get("/api/preview")
def preview() -> dict:
    """What each candidate choice would cost, without a model call.

    Which version depends on whether the vendors have answered. Once they have,
    "gating this removes Nova" is a measurement; before they have, it is a leak.
    """
    known_only = SESSION["phase"] == "draft"
    return {"gates": _gate_preview(known_only), "terms": _terms_preview(known_only),
            "known_before_quotes_only": known_only}


# ---------------------------------------------------------------------------
# The round
# ---------------------------------------------------------------------------
# A procurement round is not an instant. Mail goes out, replies arrive one at a
# time in whatever format the vendor felt like, and the buyer's actual question
# for most of the week is "where has this got to". A tool that shows a spinner
# and then a finished table has skipped the part they live in.
#
# So the round has a state, it is stored, and anyone who opens the page mid-round
# sees the same thing: who was written to, who has replied, what format it came
# in, how many lines came out of it. Every one of those is true — the extraction
# genuinely runs per document and genuinely takes time. The ONE fiction is the
# send itself, which is stubbed and says so on its own card.

def _blank_round(draft: RfxDraft) -> dict:
    names = {v["vendor_id"]: v["name"] for v in _catalogue()["vendors"]}
    return {
        "state": "idle", "started_at": None, "finished_at": None,
        "vendors": [{"vendor_id": v, "name": names.get(v, v),
                     "state": "not invited", "format": None, "lines": None,
                     "note": None} for v in (draft.vendor_ids or [])],
    }


def _round_step(round_: dict, vendor_id: str, **fields) -> None:
    for v in round_["vendors"]:
        if v["vendor_id"] == vendor_id:
            v.update(fields)
            return


def _compose_mail(d: RfxDraft) -> dict:
    """The covering mail, composed from the draft rather than written by a model.

    The buyer is about to send this to five companies. What they must be able to
    read, before they press anything, is the ACTUAL text — not a summary of the
    RFx and a promise that a mail exists. So it is built deterministically from
    the fields on the card: change the terms and this changes, with no model in
    the loop to paraphrase it into something almost right.

    The co-pilot can still rewrite it (draft_mail), and rewriting clears the
    approval.
    """
    cat = _catalogue()
    names = {v["vendor_id"]: v["name"] for v in cat["vendors"]}
    qs = {q["q_no"]: q["question"] for q in cat["questions"]}
    lines = [l for l in cat["lines"] if l["line_no"] in set(d.line_nos or [])]
    gates = [n for n in (d.gating_q_nos or []) if n in qs]
    dflt = cat["defaults"]

    subject = d.mail_subject or (
        f"{dflt.get('category', 'Category')} — annual requirement, "
        f"request for quotation")

    if d.mail_body:
        body = d.mail_body
    else:
        # A real covering note asks for the things that decide the comparison.
        # The first version asked for a rate and nothing else — no minimum
        # order, no price break, no freight basis, no validity, no lead time —
        # and then the landed cost quietly added freight the vendor had never
        # been asked about. It also told the vendor "we would rather normalise
        # your number than guess at it", which invites the exact ambiguity the
        # rest of this system exists to clean up. Ask for the unit you want,
        # and for the conversion if they cannot give it.
        gate_text = ("\n".join(f"    Q{n}. {qs[n]}" for n in gates)
                     if gates else "    (none — every answer is for information only)")
        n_q = len(d.question_nos or [])
        others = [n for n in (d.question_nos or []) if n not in gates]
        others_text = ("\n".join(f"    Q{n}. {qs[n]}" for n in others if n in qs)
                       if others else "    (none)")
        body = f"""Dear Supplier,

{dflt.get('buyer_org', 'We')} invite you to quote for our annual \
{str(dflt.get('category', '')).lower()} requirement.
The line schedule and the questionnaire are attached.

  Schedule          {len(lines)} line items
  Deliver to        {d.delivery_point or dflt.get('delivery_point', '')}
  Incoterm required {d.required_incoterm or dflt.get('required_incoterm', '')}
  Payment terms     {d.payment_terms_days} days from GRN
  Responses due     {d.response_due or '(to be confirmed)'}

WHAT TO QUOTE

  1. A rate against EVERY line, in the unit stated on that line — per piece,
     per kilogram, per set or per 100, as the schedule says. If you cannot
     quote in that unit, give us your unit AND the conversion factor you used
     (for example "Rs 42/kg, 1 box = 480 g"). Do not convert it yourself
     without telling us what you converted by.
  2. Your minimum order quantity per line, and any price break or slab — if a
     rate only holds above a volume, say so against the line it applies to. A
     rate we cannot buy at is not a rate.
  3. Freight. Quote {d.required_incoterm or dflt.get('required_incoterm', 'delivered')}. If you quote ex-works or freight-extra instead, state the freight per
     shipment and your shipments per year, because we will add it to compare
     you against a delivered quote and we would rather use your number.
  4. Taxes EXCLUSIVE. If your quote is tax-inclusive, say so and state the rate.
  5. Quote validity in days — 60 or more preferred.
  6. Your standard production lead time in days, PO to despatch.

  If any line is outside what you make, leave it blank. A blank is useful to
  us; a substitution is not.

QUESTIONNAIRE — {n_q} question{'' if n_q == 1 else 's'}, all to be answered

  {len(gates)} of them {'is' if len(gates) == 1 else 'are'} DISQUALIFYING \u2014 an unsatisfactory answer
  ends the submission regardless of price:

{gate_text}

  The remainder are for information and do not disqualify:

{others_text}

Regards,
Procurement
{dflt.get('buyer_org', '')}"""

    return {
        "to": [names.get(v, v) for v in (d.vendor_ids or [])],
        "subject": subject,
        "body": body,
        "attachments": [f"rfx_line_schedule.xlsx ({len(lines)} lines)",
                        f"quality_questionnaire.pdf "
                        f"({len(d.question_nos or [])} questions, "
                        f"{len(gates)} disqualifying)"],
        "stub_note": "Sending is stubbed: no mail leaves the building. The five "
                     "replies are documents that already exist in this repo, and "
                     "reading them is the part that is real.",
        "approved": bool(d.mail_approved),
        "missing": d.missing(),
    }


@app.get("/api/mail")
def mail() -> dict:
    """Exactly what goes out, before anyone presses anything."""
    return _compose_mail(SESSION["draft"])


@app.get("/api/round")
def round_state() -> dict:
    """Where this round has got to. Readable at any moment, by anyone."""
    return SESSION["round"]


def _issue(draft: RfxDraft, sess: dict | None = None) -> None:
    """Run the whole pipeline against the RFx the buyer just authored.

    Lives here rather than in analyst/author.py because this module is a
    composition root and that one is a leaf. A leaf importing `pipeline` would
    quietly invert the dependency the whole architecture rests on.
    """
    import pipeline
    sess = sess if sess is not None else _session()
    p = sess.get("db")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
    pipeline.run(fresh=True, verbose=False, draft=draft, db_path=p)
    sess["phase"] = "comparison"


def db():
    """This visitor's store. Falls back to the shared one for a local run."""
    p = SESSION.get("db")
    if p is not None and p.exists():
        return repo.connect(p)
    if not DB_PATH.exists():
        raise HTTPException(503, "Database not built. Run `python -m pipeline` first.")
    return repo.connect(DB_PATH)


def _require_issued(what: str) -> None:
    """Refuse to describe responses that have not arrived.

    Same rule as the drafting screen, applied at the door rather than in the
    markup. There is no comparison before there are quotes; an endpoint that
    answers anyway is a back way into the thing the screen is careful not to
    show, and "the UI does not call it" is not a property of the system.
    """
    if SESSION["phase"] == "draft":
        raise HTTPException(
            409, f"No {what} yet — the RFx has not been issued. "
                 f"Nothing has come back from any vendor.")


@app.middleware("http")
async def _per_visitor_session(request, call_next):
    """A cookie, so two people opening the same link get two tenders."""
    sid = request.cookies.get(SID_COOKIE) or uuid.uuid4().hex
    token = _CURRENT_SID.set(sid)
    try:
        response = await call_next(request)
    finally:
        _CURRENT_SID.reset(token)
    response.set_cookie(SID_COOKIE, sid, max_age=86400, samesite="lax",
                        httponly=True)
    return response


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
    """What the screen is allowed to know, which depends on what has happened.

    While the buyer is still writing the RFx this used to return the finished
    comparison, every vendor's qualification, the contradiction list and the
    injection log — the whole answer, one devtools tab away from a screen whose
    premise is that nothing has been sent. The page never drew any of it, which
    made it worse rather than better: an invariant that holds only because
    nobody happens to read the payload is not an invariant.
    """
    conn = db()
    rfx = dict(conn.execute("SELECT * FROM rfx LIMIT 1").fetchone())
    if SESSION["phase"] == "draft":
        return {"phase": "draft", "provenance": _provenance(),
                "threshold": REVIEW_THRESHOLD,
                # The template's own header fields. The buyer wrote these, or
                # inherited them from last year's tender; nothing here came out
                # of a reply.
                "rfx": {k: rfx.get(k) for k in
                        ("rfx_id", "title", "buyer_org", "category", "currency",
                         "delivery_point", "required_incoterm",
                         "required_payment_terms", "cost_of_capital_pct")}}
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
    # How many documents the model actually read, out of how many arrived. A
    # per-document fallback means this can legitimately be 4 of 5, and saying
    # "extraction by GLM-4.6V" while one document came from the fixture path
    # would be the same lie the whole provenance chip exists to prevent.
    try:
        total = len(json.loads(
            (DATA / "ground_truth.json").read_text(encoding="utf-8"))["submissions"])
    except Exception:                                        # noqa: BLE001
        total = len(runs)
    partial = len(runs) < total
    return {"mode": "partial" if partial else "recorded",
            "label": (f"extraction by {', '.join(models)}"
                      + (f" — {len(runs)} of {total} documents" if partial else "")),
            "detail": (f"{len(runs)} of {total} documents parsed by a real model "
                       f"run, recorded {min(r['recorded_at'] for r in runs)} and "
                       f"replayed verbatim. "
                       + (f"The other {total - len(runs)} fell back to the fixture "
                          f"path because the model's output did not validate — "
                          f"named here rather than averaged away. "
                          if partial else "")
                       + "Re-recorded on every deploy."),
            "runs": runs}


@app.get("/api/comparison")
def comparison(lines: str | None = None, vendors: str | None = None) -> dict:
    _require_issued("a comparison")
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
    """The queue as DECISIONS, not as cells.

    Twenty-eight cells at threshold 0.82 is the known weakness of this build,
    and shortening it by raising the threshold would shorten it by hiding
    errors. But twenty-eight cells are not twenty-eight decisions: they are
    three — an inch-to-millimetre conversion, an incumbent who wrote "rest same
    as last year", and vendors whose word for a thing is not the buyer's word.
    Three a buyer can actually hold. Twenty-eight they accept in a block, which
    is the failure the queue exists to prevent, arriving by a different route.
    """
    _require_issued("review queue")
    conn = db()
    groups = repo.group_reviews(conn)
    total = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    return {"open": total, "groups": groups, "threshold": REVIEW_THRESHOLD,
            "items": [i for g in groups for i in g["items"]][:limit]}


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
        _apply_correction(conn, review_id, d.value or "")
    left = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    return {"ok": True, "open": left}


class BulkDecision(BaseModel):
    review_ids: list[int]
    reviewer: str = "buyer"


@app.post("/api/reviews/accept")
def accept_many(d: BulkDecision) -> dict:
    """Accept a whole cause at once.

    Deliberately accept-only. Accepting a group says "this convention is right",
    which is one judgement about one thing and is exactly what the grouping is
    for. Correcting a group would say "every one of these rates is the same
    wrong number", which is never true — corrections stay per cell.
    """
    conn = db()
    ids = [int(i) for i in d.review_ids][:200]
    if not ids:
        return {"ok": False, "open": conn.execute(
            "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]}
    q = ",".join("?" * len(ids))
    conn.execute(f"UPDATE review_item SET status='accepted', reviewer=?, "
                 f"reviewed_at=datetime('now') WHERE id IN ({q}) AND status='open'",
                 (d.reviewer, *ids))
    conn.commit()
    left = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    return {"ok": True, "accepted": len(ids), "open": left}


def _apply_correction(conn, review_id: int, value: str) -> None:
    """Put a human's correction into the comparison, not just into the log.

    Before this, `Correct…` wrote an audit row and the cell on screen did not
    move. That is worse than having no review queue: it invites a buyer to fix a
    number, shows them their fix had no effect, and keeps the wrong figure in
    every total downstream. A review queue that does not change the answer is
    theatre, and the whole trust argument rests on it not being.

    The correction is a rate in the VENDOR's own terms, so it is re-normalised
    through the same eight deterministic steps as every other cell rather than
    written straight into landed cost. A human correcting "Rs 9.16 / set" has
    not told us the landed cost; they have told us the rate, and the arithmetic
    is still the machine's job.
    """
    import json as _json
    import re as _re

    from contracts.quote import GroundTruth, QuoteBasis, VendorLineQuote
    from normalize.engine import normalise_line

    row = conn.execute(
        "SELECT vendor_id, line_no, field FROM review_item WHERE id=?",
        (review_id,)).fetchone()
    if not row or row["field"] != "rate":
        return                       # only rate corrections re-price a cell
    vid, ln = row["vendor_id"], row["line_no"]

    m = _re.search(r"-?\d+(?:[.,]\d+)?", (value or "").replace(",", ""))
    if not m:
        return                       # not a number; the audit row still stands
    rate = float(m.group(0))

    gt = GroundTruth.model_validate(
        _json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    line = next((l for l in gt.rfx.lines if l.line_no == ln), None)
    sub = next((x for x in gt.submissions if x.vendor.vendor_id == vid), None)
    if line is None or sub is None:
        return

    prior = next((q for q in sub.line_quotes if q.line_no == ln), None)
    q = VendorLineQuote(
        line_no=ln, rate=rate,
        currency=prior.currency if prior else sub.vendor.currency,
        basis=prior.basis if prior else QuoteBasis("per_piece"),
        refers_to_prior_contract=False,
        excludes_sub_component=prior.excludes_sub_component if prior else False,
        tooling_inr=prior.tooling_inr if prior else None,
        tooling_amortised=prior.tooling_amortised if prior else False,
        note=f"human correction by review #{review_id}")
    units = sum(l.annual_qty for l in gt.rfx.lines
                for qq in sub.line_quotes if qq.line_no == l.line_no) or 1
    n = normalise_line(q, line, sub.vendor, gt, units)

    caveats = list(n.caveats) + [
        "Value corrected by a human reviewer and re-normalised through the "
        "same eight steps. Original extraction is retained in the review log."]
    conn.execute(
        "UPDATE normalised_line SET landed_inr=?, state=?, base_inr=?, "
        "freight_inr=?, tooling_inr=?, discount_inr=?, npv_adjustment_inr=?, "
        "caveats=?, unresolved_reason=NULL, missing_fact=NULL, "
        "extraction_confidence=1.0, match_confidence=1.0 "
        "WHERE vendor_id=? AND line_no=?",
        (n.landed_inr, n.state.value, n.base_inr, n.freight_inr, n.tooling_inr,
         n.discount_inr, n.npv_adjustment_inr, _json.dumps(caveats), vid, ln))
    conn.commit()


class Ask(BaseModel):
    question: str


@app.post("/api/ask")
def ask(a: Ask):
    """Server-sent events. Blocks reach the UI as they are produced, so a
    multi-step answer shows its working rather than appearing all at once."""
    conn = db()
    sess = _session()               # same reason as /api/issue: see below
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
    drafting = sess["phase"] == "draft"
    if drafting:
        tools = AuthorTools(sess["draft"], _catalogue())
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
            if drafting and sess["draft"].issued and not issued:
                issued = True
        if issued:
            # The vendors "reply". Extraction, matching, normalisation and
            # allocation all run now, against the RFx the buyer just wrote.
            yield ("data: " + json.dumps({"kind": "status",
                                          "payload": "reading five responses…"}) + "\n\n")
            try:
                _issue(sess["draft"], sess)
                yield "data: " + json.dumps({"kind": "issued"}) + "\n\n"
            except Exception as e:                            # noqa: BLE001
                sess["draft"].issued = False
                body = {"type": "refusal", "question": a.question,
                        "reason": f"The RFx went out but reading the responses "
                                  f"failed: {type(e).__name__}: {e}",
                        "would_need": ["The draft is intact — try issuing again."]}
                yield "data: " + json.dumps({"kind": "block", "payload": body}) + "\n\n"
        yield "data: {\"kind\": \"done\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/issue")
def issue_round():
    """Send the RFx and read what comes back, reporting as it goes.

    A button rather than a sentence to the model, for the same reason the
    pickers write their own field: sending a tender is not a thing to route
    through a paraphrase. The co-pilot's job ended when the buyer approved the
    mail.

    The send is stubbed — that is the one stub the brief allows and the card
    says so on its face. Everything after it is real work on real documents,
    which is why it is worth watching.
    """
    # Bind the session HERE. The generator below runs while the response is
    # streaming, which is after the middleware has reset the per-request
    # context — so SESSION inside it would resolve to the wrong visitor, and in
    # testing resolved to the fallback and wrote its database there.
    sess = _session()
    d = sess["draft"]
    gaps = d.missing()
    if gaps:
        raise HTTPException(409, f"Still missing {', '.join(gaps)}.")
    if not d.mail_body:
        # The buyer approved exactly what /api/mail showed them, and that text is
        # composed from the draft rather than written by a model — so recomposing
        # it here yields the same bytes. Storing it makes "what was sent" a
        # recorded fact rather than something re-derived later from fields that
        # may have moved on.
        composed = _compose_mail(d)
        d.mail_subject = d.mail_subject or composed["subject"]
        d.mail_body = composed["body"]
    if not d.mail_approved:
        raise HTTPException(409, "The covering mail has not been approved.")

    sess["round"] = _blank_round(d)
    r = sess["round"]
    r["state"] = "sending"
    r["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def stream():
        def ev(kind, payload):
            return f"data: {json.dumps({'kind': kind, 'payload': payload})}\n\n"

        for v in r["vendors"]:
            v["state"] = "mail sent"
            v["note"] = "stubbed — no mail left the building"
        r["state"] = "awaiting replies"
        yield ev("round", r)

        d.issued = True
        try:
            import pipeline

            # The pipeline runs on a thread and its progress comes back through
            # a queue, so each vendor's row changes WHEN that document is read
            # rather than all five flipping at the end. The difference matters:
            # a progress display that is really a replay is a loading animation
            # with a story attached, and this one is meant to be the true state
            # of the round.
            q: queue.Queue = queue.Queue()
            done_marker = object()

            def work():
                try:
                    dbp = sess.get("db")
                    if dbp is not None:
                        dbp.parent.mkdir(parents=True, exist_ok=True)
                    pipeline.run(fresh=True, verbose=False, draft=d,
                                 on_progress=q.put, db_path=dbp)
                except Exception as exc:                      # noqa: BLE001
                    q.put(exc)
                finally:
                    q.put(done_marker)

            th = threading.Thread(target=work, daemon=True)
            th.start()
            failure = None
            while True:
                e = q.get()
                if e is done_marker:
                    break
                if isinstance(e, Exception):
                    failure = e
                    continue
                if e["state"] == "reading":
                    _round_step(r, e["vendor_id"], state="reply received",
                                format=e.get("format"),
                                note=f"replied by {e.get('format')}")
                else:
                    ms = e.get("ms")
                    took = (f" in {ms/1000:.1f}s" if ms and ms >= 1000
                            else f" in {ms}ms" if ms else "")
                    note = f"{e.get('lines')} lines read{took}"
                    if e.get("degraded"):
                        note += " \u00b7 fell back to the fixture path"
                    if e.get("injection"):
                        note += " \u00b7 instructions found in the document, logged"
                    _round_step(r, e["vendor_id"], state="quote read",
                                lines=e.get("lines"), note=note)
                yield ev("round", r)
            th.join(timeout=5)
            if failure is not None:
                raise failure
            r["state"] = "complete"
            r["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            sess["phase"] = "comparison"
            yield ev("round", r)
            yield ev("done", {"phase": "comparison"})
        except Exception as exc:                              # noqa: BLE001
            d.issued = False
            r["state"] = "failed"
            r["error"] = f"{type(exc).__name__}: {exc}"
            yield ev("round", r)
            yield ev("done", {"phase": "draft"})

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
    SESSION["round"] = _blank_round(d)
    for v in SESSION["round"]["vendors"]:
        v.update(state="quote read", note="issued from the template, unauthored")
    SESSION["round"]["state"] = "complete"
    _issue(d)
    return {"ok": True, "phase": SESSION["phase"]}


class DraftEdit(BaseModel):
    line_nos: list[int] | None = None
    vendor_ids: list[str] | None = None
    question_nos: list[int] | None = None
    gating_q_nos: list[int] | None = None
    payment_terms_days: int | None = None
    response_due: str | None = None
    mail_subject: str | None = None
    mail_body: str | None = None
    mail_approved: bool | None = None
    qty_overrides: dict[int, int] | None = None
    extra_lines: list[dict] | None = None


@app.post("/api/draft")
def edit_draft(e: DraftEdit) -> dict:
    """Edit the draft directly, with no model call.

    Ticking twelve line items is data entry, not judgement. Routing it through
    the co-pilot would cost a model call per click, take a second each time, and
    occasionally get it wrong. The model is for the decisions; the picker writes
    to the draft itself.
    """
    d = SESSION["draft"]
    for field in ("line_nos", "vendor_ids", "question_nos", "gating_q_nos",
                  "payment_terms_days", "response_due", "mail_subject",
                  "mail_body", "mail_approved", "qty_overrides", "extra_lines"):
        v = getattr(e, field)
        if v is not None:
            setattr(d, field, v)
    if e.question_nos is not None:
        # An explicit choice, including an empty one. Gates can only be a subset
        # of what is actually asked.
        d.questions_chosen = True
        d.gating_q_nos = [n for n in d.gating_q_nos if n in d.question_nos]
    elif not d.question_nos and not d.questions_chosen:
        d.question_nos = [q["q_no"] for q in _catalogue()["questions"]]
    # Editing the wording un-approves it. Approval is approval of THIS text.
    if (e.mail_body is not None or e.mail_subject is not None) \
            and e.mail_approved is None:
        d.mail_approved = False
    return {"ok": True, "draft": json.loads(d.model_dump_json()),
            "missing": d.missing()}


@app.get("/api/draft")
def get_draft() -> dict:
    d = SESSION["draft"]
    return {"draft": json.loads(d.model_dump_json()), "missing": d.missing(),
            "phase": SESSION["phase"]}


@app.post("/api/reset")
def reset() -> dict:
    """Back to an empty chat and a blank RFx, so the flow can be demonstrated
    twice without a redeploy."""
    SESSION["phase"] = "draft"
    SESSION["draft"] = RfxDraft()
    SESSION["round"] = {"state": "idle", "vendors": []}
    p = SESSION.get("db")
    if p is not None:
        p.unlink(missing_ok=True)
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
    _require_issued("set of options")
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


@app.get("/api/spend")
def spend() -> dict:
    """Where the money is, and where the competition is.

    Two questions the grid cannot answer, because a table sorted by line number
    hides both. Thirty lines look like thirty equal decisions; they are not —
    one layer-pad line is a quarter of the award, and a buyer with a week has
    to know which five lines are worth a phone call.

    And a line only rewards negotiation if somebody else wanted it. The spread
    between the best and worst price on a line is the closest thing in an RFx
    to a measure of how contested it was.

    Both are arithmetic over stored cells. No model, and no ranking the buyer
    cannot reproduce from the table.
    """
    _require_issued("spend analysis")
    conn = db()
    rows = [dict(r) for r in conn.execute(
        "SELECT l.line_no, l.code, l.description, l.annual_qty, l.uom,"
        "       MIN(n.landed_inr) AS best, MAX(n.landed_inr) AS worst,"
        "       COUNT(n.landed_inr) AS priced "
        "FROM rfx_line l LEFT JOIN normalised_line n"
        "  ON n.line_no = l.line_no AND n.landed_inr IS NOT NULL "
        "GROUP BY l.line_no ORDER BY l.line_no").fetchall()]
    out = []
    for r in rows:
        best = r["best"]
        spend_inr = (best or 0) * r["annual_qty"]
        spread = (((r["worst"] - best) / best * 100.0)
                  if best and r["worst"] and r["priced"] > 1 else None)
        out.append({
            "line_no": r["line_no"], "code": r["code"],
            "description": r["description"], "uom": uom_label(r["uom"]),
            "annual_qty": r["annual_qty"], "best_inr": best,
            "worst_inr": r["worst"], "priced_by": r["priced"],
            "annual_inr": round(spend_inr, 2),
            "spread_pct": round(spread, 1) if spread is not None else None})
    total = sum(x["annual_inr"] for x in out) or 1.0
    for x in out:
        x["share_pct"] = round(x["annual_inr"] / total * 100.0, 2)

    # How few lines carry most of the money. The buyer's week is finite and this
    # is the number that decides where it goes.
    ranked = sorted(out, key=lambda x: -x["annual_inr"])
    run, head = 0.0, 0
    for x in ranked:
        run += x["annual_inr"]
        head += 1
        if run / total >= 0.8:
            break
    widest = max((x for x in out if x["spread_pct"] is not None),
                 key=lambda x: x["spread_pct"], default=None)
    return {"lines": out, "total_inr": round(total, 2),
            "lines_for_80pct": head,
            "widest_spread": widest,
            "note": "Annual spend uses the cheapest landed rate on each line; "
                    "the spread is best against worst among vendors who priced it."}


# ---------------------------------------------------------------------------
# Round two, and the summary that sends you into it
# ---------------------------------------------------------------------------

def _rows_from_db(conn) -> list:
    from contracts.normalized import CellState, NormalisedLine
    from contracts.rfx import Uom
    return [NormalisedLine(
        vendor_id=r["vendor_id"], line_no=r["line_no"], buyer_uom=Uom(r["buyer_uom"]),
        as_quoted=r["as_quoted"], landed_inr=r["landed_inr"],
        state=CellState(r["state"]), freight_inr=r["freight_inr"],
        missing_fact=r["missing_fact"], unresolved_reason=r["unresolved_reason"])
        for r in conn.execute("SELECT * FROM normalised_line").fetchall()]


def _session_gt():
    """This session's ground truth: the authored RFx, plus any round-two replies
    already folded in. Everything downstream re-derives from it."""
    import pipeline
    gt = pipeline.load_gt()
    d = SESSION["draft"]
    if d.issued:
        gt = pipeline.apply_draft(gt, d)
    done = SESSION.get("clarified") or []
    if done:
        gt, _ = pipeline.apply_clarifications(gt, done)
    return gt


@app.get("/api/gaps")
def gaps() -> dict:
    """What is still missing from each vendor, and what asking would be worth."""
    _require_issued("gap analysis")
    from analyst.gaps import gaps_for
    conn = db()
    gt = _session_gt()
    done = set(SESSION.get("clarified") or [])
    have = {c.vendor_id for c in gt.clarifications}
    out = []
    for e in gaps_for(gt, _rows_from_db(conn)):
        e["already_asked"] = e["vendor_id"] in done
        # Only offer to write to a vendor who would actually write back. A
        # button that sends a mail into a void is worse than no button.
        e["can_ask"] = e["vendor_id"] in have and e["vendor_id"] not in done
        out.append(e)
    return {"vendors": out, "asked": sorted(done)}


@app.get("/api/followup/{vendor_id}")
def followup(vendor_id: str) -> dict:
    """The follow-up mail, composed from the gaps rather than written."""
    _require_issued("follow-up")
    from analyst.gaps import compose_followup, gaps_for
    conn = db()
    gt = _session_gt()
    entry = next((e for e in gaps_for(gt, _rows_from_db(conn))
                  if e["vendor_id"] == vendor_id), None)
    if entry is None:
        raise HTTPException(404, f"Nothing to ask {vendor_id}.")
    m = compose_followup(gt, entry)
    m["stub_note"] = ("Sending is stubbed. Their reply is a document that "
                      "already exists in this repo, and reading it is the part "
                      "that is real.")
    return m


@app.post("/api/followup/{vendor_id}")
def send_followup(vendor_id: str):
    """Send it, read what comes back, and re-derive everything from it.

    The second half of the loop this project's one-pager calls the moat, and
    shipped for a week as a bullet in "what I would build next". A reply that
    only updated a display would be the same failure as a review queue that does
    not change the answer — so the whole pipeline runs again, and the screen
    says what moved.
    """
    sess = _session()
    if sess["phase"] != "comparison":
        raise HTTPException(409, "No round has been issued.")
    import pipeline
    gt0 = pipeline.load_gt()
    if not any(c.vendor_id == vendor_id for c in gt0.clarifications):
        raise HTTPException(404, f"{vendor_id} has nothing to send back.")

    def ev(kind, payload):
        return f"data: {json.dumps({'kind': kind, 'payload': payload})}\n\n"

    def stream():
        try:
            yield ev("status", {"state": "sent",
                                "text": f"Follow-up sent to {vendor_id}."})
            done = list(sess.get("clarified") or [])
            if vendor_id not in done:
                done.append(vendor_id)
            sess["clarified"] = done

            gt = pipeline.apply_draft(gt0, sess["draft"]) if sess["draft"].issued else gt0
            gt, applied = pipeline.apply_clarifications(gt, done)
            mine = next((a for a in applied if a["vendor_id"] == vendor_id), {})
            yield ev("status", {"state": "replied",
                                "text": f"{vendor_id} replied.",
                                "changed": mine.get("changed", []),
                                "declined": mine.get("declined")})

            before = _snapshot(db())
            dbp = sess.get("db")
            if dbp is not None:
                dbp.parent.mkdir(parents=True, exist_ok=True)
            pipeline.run(fresh=True, verbose=False, gt=gt, db_path=dbp)
            after = _snapshot(db())
            yield ev("applied", {"vendor_id": vendor_id,
                                 "changed": mine.get("changed", []),
                                 "declined": mine.get("declined"),
                                 "before": before, "after": after})
            yield ev("done", {})
        except Exception as exc:                              # noqa: BLE001
            yield ev("error", {"text": f"{type(exc).__name__}: {exc}"})
            yield ev("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream")


def _snapshot(conn) -> dict:
    """The three numbers a clarification can move."""
    n = dict(conn.execute(
        "SELECT COUNT(*) AS cells, SUM(state='unresolved') AS unresolved "
        "FROM normalised_line").fetchone())
    q = conn.execute("SELECT COUNT(*) c FROM vendor WHERE qualified=1").fetchone()["c"]
    r = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    return {"cells": n["cells"], "unresolved": n["unresolved"] or 0,
            "qualified": q, "open_reviews": r}


def _inr(n: float) -> str:
    """Rupees, grouped the way every other number on this screen is.

    `f"{n:,.0f}"` gives 7,514,446 where the table, the memo and the charts all
    say 75,14,446. One screen, two grouping conventions, both for money, is the
    kind of detail a buyer notices and a demo does not.
    """
    s_ = f"{abs(int(round(n)))}"
    if len(s_) > 3:
        head, tail = s_[:-3], s_[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s_ = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "\u20b9" + s_


@app.get("/api/summary")
def summary() -> dict:
    """What came back, and what to do about it.

    A buyer does not want a table, they want to know what to do on Monday. The
    table is the evidence for the answer, not the answer.
    """
    _require_issued("summary")
    from allocate.subsets import options as build_options
    from analyst.gaps import gaps_for
    conn = db()
    gt = _session_gt()
    rows = _rows_from_db(conn)
    cards = build_options(gt, rows)
    live = [c for c in cards if not c.get("unavailable")]
    sp = spend()
    gaps_ = gaps_for(gt, rows)
    vendors = [dict(r) for r in conn.execute(
        "SELECT vendor_id, name, qualified, disqualified_because FROM vendor").fetchall()]
    for v in vendors:
        v["disqualified_because"] = json.loads(v["disqualified_because"] or "[]")
    out_v = [v for v in vendors if not v["qualified"]]
    unresolved = sum(1 for r in rows if str(r.state) .endswith("unresolved"))

    suggestions = []
    if len(live) > 1:
        gap = live[-1]["total_inr"] - live[0]["total_inr"]
        suggestions.append({
            "do": f"Split rather than single-source, unless one throat to choke "
                  f"is worth {_inr(gap)} a year.",
            "because": f"{live[0]['label']} is {_inr(live[0]['total_inr'])} "
                       f"across {len(live[0]['vendors'])} vendors; the "
                       f"single-vendor option is {_inr(live[-1]['total_inr'])}."})
    if sp["lines_for_80pct"]:
        suggestions.append({
            "do": f"Negotiate the top {sp['lines_for_80pct']} lines and leave "
                  f"the rest alone.",
            "because": f"They are 80% of the {_inr(sp['total_inr'])}. The "
                       f"other {len(sp['lines']) - sp['lines_for_80pct']} lines "
                       f"together are the remaining fifth."})
    w = sp.get("widest_spread")
    if w and w.get("spread_pct", 0) > 25:
        suggestions.append({
            "do": f"Run a second round on line {w['line_no']} first.",
            "because": f"Best and worst are {w['spread_pct']:.0f}% apart on it, "
                       f"which is as contested as this schedule gets."})
    askable = [g for g in gaps_ if g["units_at_stake"] > 0]
    if askable:
        suggestions.append({
            "do": f"Write back to {askable[0]['vendor'].split()[0]} before you "
                  f"decide anything.",
            "because": f"{askable[0]['asks'][0]['what'].capitalize()} — "
                       f"{askable[0]['units_at_stake']:,} units of the schedule "
                       f"hang on it."})
    if unresolved:
        suggestions.append({
            "do": f"Do not treat the {unresolved} empty cells as zero.",
            "because": "They are lines nobody priced in a way we can compare. "
                       "The follow-up above is how they get filled."})

    return {"options": cards, "spend": {k: sp[k] for k in
                                        ("total_inr", "lines_for_80pct",
                                         "widest_spread")},
            "disqualified": out_v, "unresolved": unresolved,
            "gaps": gaps_, "suggestions": suggestions}


@app.get("/api/memo")
def memo(strategy: str | None = None) -> dict:
    """The decision record, for the option the buyer actually picked.

    It used to write the memo for the cheapest split whatever card the buyer was
    looking at, which makes the three options a display rather than a choice —
    and the single-vendor card exists precisely because a buyer sometimes takes
    the more expensive one on purpose.
    """
    _require_issued("award memo")
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
    chosen = allocs[0]
    if strategy:
        chosen = next((a for a in allocs if a.strategy == strategy), chosen)
    return {"markdown": memo_mod.build(conn, chosen), "strategy": chosen.strategy,
            "was_cheapest": chosen.strategy == allocs[0].strategy}


@app.get("/api/assumptions")
def assumptions() -> dict:
    _require_issued("set of assumptions")
    conn = db()
    return {"rows": [dict(r) for r in conn.execute(
        "SELECT * FROM assumption ORDER BY key").fetchall()]}
