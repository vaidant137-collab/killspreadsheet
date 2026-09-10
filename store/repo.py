"""
The store. Plain sqlite3, no ORM — the analyst writes SQL against these tables
and the schema is small enough to hold in your head, which is the point.

Read access for the analyst is deliberately narrow: `query()` refuses anything
that is not a single SELECT. That is not paranoia about the model, it is the
same reason extraction is schema-constrained — a tool that can only read cannot
be talked into writing, whatever a vendor document says.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DB_PATH, ROOT

SCHEMA = Path(__file__).parent / "schema.sql"
_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma)\b", re.I)


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init(path: Path | str = DB_PATH, *, fresh: bool = False) -> sqlite3.Connection:
    p = Path(path)
    if fresh and p.exists():
        p.unlink()
        for suffix in ("-wal", "-shm"):
            q = Path(str(p) + suffix)
            if q.exists():
                q.unlink()
    c = connect(p)
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    c.commit()
    return c


def query(conn: sqlite3.Connection, sql: str, limit: int = 500) -> list[dict[str, Any]]:
    """Read-only. One statement, SELECT or WITH only.

    The analyst's whole database access goes through here. Refusing writes at
    the tool boundary means no prompt, however crafted, can mutate the record
    the award memo is built from.
    """
    s = sql.strip().rstrip(";")
    if ";" in s:
        raise ValueError("one statement at a time")
    if not re.match(r"^\s*(select|with)\b", s, re.I):
        raise ValueError("read-only: SELECT or WITH statements only")
    if _WRITE.search(s):
        raise ValueError("read-only: this tool cannot modify the record")
    if not re.search(r"\blimit\b", s, re.I):
        s += f" LIMIT {limit}"
    return [dict(r) for r in conn.execute(s).fetchall()]


def _j(v) -> str | None:
    return json.dumps(v) if v else None


# ---------------------------------------------------------------------------

def load_rfx(conn, gt) -> None:
    r = gt.rfx
    conn.execute(
        "INSERT OR REPLACE INTO rfx (rfx_id,title,buyer_org,category,currency,"
        "issued_date,response_due,award_target,delivery_point,required_incoterm,"
        "required_payment_terms,cost_of_capital_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (r.rfx_id, r.title, r.buyer_org, r.category, r.currency, r.issued_date,
         r.response_due, r.award_target, r.delivery_point, r.required_incoterm,
         r.required_payment_terms, r.cost_of_capital_pct))
    for l in r.lines:
        conn.execute(
            "INSERT OR REPLACE INTO rfx_line "
            "(line_no,code,description,style,ply,length_mm,width_mm,height_mm,"
            " flute,liner_gsm,gsm_stack,bursting_factor,print_spec,annual_qty,"
            " uom,unit_weight_g,food_contact,requires_tooling,sub_components,"
            " capacity_band) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (l.line_no, l.code, l.description, l.style.value, l.ply,
             l.dims.length_mm, l.dims.width_mm, l.dims.height_mm, l.flute,
             l.liner_gsm, l.gsm_stack, l.bursting_factor, l.print_spec,
             l.annual_qty, l.uom.value, l.unit_weight_g, int(l.food_contact),
             int(l.requires_tooling), _j(l.sub_components), l.capacity_band))
    conn.commit()


def load_vendors(conn, gt, qualification: dict | None = None) -> None:
    for s in gt.submissions:
        v = s.vendor
        q = (qualification or {}).get(v.vendor_id)
        conn.execute(
            "INSERT OR REPLACE INTO vendor "
            "(vendor_id,name,city,incumbent,reply_format,dimension_system,"
            " unit_wording,currency,incoterm,tax_basis,payment_days,validity_days,"
            " moq_pieces,fx_rate_at_quote,freight_inr_per_shipment,"
            " shipments_per_year,early_payment_discount_pct,"
            " early_payment_within_days,qualified) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (v.vendor_id, v.name, v.city, int(v.incumbent), v.reply_format,
             v.dimension_system, v.unit_wording, v.currency, v.incoterm.value,
             v.tax_basis.value, v.payment_days, v.validity_days, v.moq_pieces,
             v.fx_rate_at_quote, v.freight_inr_per_shipment, v.shipments_per_year,
             v.early_payment_discount_pct, v.early_payment_within_days,
             int(q.qualified) if q else None))
        if q and q.disqualified_because:
            conn.execute("UPDATE vendor SET disqualified_because=? WHERE vendor_id=?",
                         (_j(q.disqualified_because), v.vendor_id))
    conn.commit()


def load_documents(conn, gt) -> None:
    """Register every file that arrived, so evidence has something to point at."""
    gen, att = ROOT / "data" / "generated", ROOT / "data" / "attachments"
    kind_of = {".xlsx": "xlsx", ".pdf": "pdf", ".docx": "docx", ".jpg": "image",
               ".jpeg": "image", ".png": "image", ".eml": "email", ".json": "json"}
    for s in gt.submissions:
        vid = s.vendor.vendor_id
        for d in (gen, att):
            for p in sorted(d.glob(f"{vid}*")):
                role = ("questionnaire" if "questionnaire" in p.name
                        else "brochure" if "profile" in p.name
                        else "quote" if d is gen else "evidence")
                conn.execute(
                    "INSERT OR REPLACE INTO source_doc "
                    "(doc_id,vendor_id,path,kind,role,pages,bytes) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (p.name, vid, str(p.relative_to(ROOT)),
                     kind_of.get(p.suffix.lower(), "other"), role, None,
                     p.stat().st_size))
    conn.commit()


def load_quotes(conn, gt, extracted) -> None:
    for e in extracted:
        ev_id = None
        if e.evidence:
            ev_id = e.evidence.evidence_id
            conn.execute("INSERT OR REPLACE INTO evidence "
                         "(evidence_id,doc_id,locator,snippet,page,bbox) "
                         "VALUES (?,?,?,?,?,?)",
                         (ev_id, e.evidence.doc_id, e.evidence.locator,
                          e.evidence.snippet, e.evidence.page, e.evidence.bbox))
        conn.execute(
            "INSERT INTO vendor_quote_line "
            "(vendor_id,line_no,vendor_label,rate,currency,basis,"
            " refers_to_prior_contract,excludes_sub_component,tooling_inr,"
            " tooling_amortised,note,evidence_id,extraction_confidence,"
            " match_confidence,match_rationale) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.vendor_id, e.line_no, e.vendor_label, e.rate, e.currency, e.basis,
             int(e.refers_to_prior_contract), int(e.excludes_sub_component),
             e.tooling_inr, int(e.tooling_amortised), e.note, ev_id,
             e.extraction_confidence, e.match_confidence, e.match_rationale))
    conn.commit()


def load_normalised(conn, rows) -> None:
    for n in rows:
        conn.execute(
            "INSERT OR REPLACE INTO normalised_line "
            "(vendor_id,line_no,buyer_uom,as_quoted,landed_inr,state,"
            " unresolved_reason,missing_fact,assumptions_used,caveats,base_inr,"
            " freight_inr,tooling_inr,discount_inr,npv_adjustment_inr,"
            " evidence_id,extraction_confidence,match_confidence) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (n.vendor_id, n.line_no, n.buyer_uom.value, n.as_quoted, n.landed_inr,
             n.state.value, n.unresolved_reason, n.missing_fact,
             _j(n.assumptions_used), _j(n.caveats), n.base_inr, n.freight_inr,
             n.tooling_inr, n.discount_inr, n.npv_adjustment_inr, n.evidence_ref,
             n.extraction_confidence, n.match_confidence))
    conn.commit()


def load_assumptions(conn, assumptions: dict) -> None:
    for a in assumptions.values():
        conn.execute("INSERT OR REPLACE INTO assumption "
                     "(key,label,value,unit,source,editable) VALUES (?,?,?,?,?,?)",
                     (a.key, a.label, str(a.value), a.unit, a.source, int(a.editable)))
    conn.commit()


def load_questionnaire(conn, gt) -> None:
    for s in gt.submissions:
        for a in s.questionnaire:
            q = next(x.question for x in gt.rfx.questionnaire if x.q_no == a.q_no)
            # A questionnaire answer that cites a document needs an evidence
            # row to point at, so the drawer can open the certificate the answer
            # claims -- which is the whole mechanism behind catching Nova.
            ev_id = None
            if a.evidence_file:
                ev_id = f"{s.vendor.vendor_id}-q{a.q_no}"
                conn.execute(
                    "INSERT OR REPLACE INTO evidence "
                    "(evidence_id,doc_id,locator,snippet,page,bbox) "
                    "VALUES (?,?,?,?,?,?)",
                    (ev_id, a.evidence_file, "document", None, 1, None))
            note = None
            if a.contradicted_by_evidence:
                att = next((t for t in s.attachments if t.filename == a.evidence_file), None)
                if att and att.valid_until:
                    note = (f"The attached {att.filename} expired {att.valid_until}, "
                            f"which contradicts this answer.")
            conn.execute(
                "INSERT INTO questionnaire_answer "
                "(vendor_id,q_no,question,answer,evidence_id,"
                " contradicted_by_evidence,contradiction_note) VALUES (?,?,?,?,?,?,?)",
                (s.vendor.vendor_id, a.q_no, q, a.answer, ev_id,
                 int(a.contradicted_by_evidence), note))
    conn.commit()


def queue_reviews(conn, rows, threshold: float) -> int:
    """Everything below the confidence threshold becomes a human decision.

    Queue length is a displayed product metric, not a hidden one: tune the
    threshold until a person actually reads the queue. A 60-item queue gets
    rubber-stamped and the trust layer becomes theatre.
    """
    n = 0
    for r in rows:
        conf = min(r.extraction_confidence, r.match_confidence)
        if conf >= threshold:
            continue
        conn.execute(
            "INSERT INTO review_item (vendor_id,line_no,field,proposed_value,"
            "confidence,evidence_id,status) VALUES (?,?,?,?,?,?,'open')",
            (r.vendor_id, r.line_no, "rate", r.as_quoted, conf, r.evidence_ref))
        n += 1
    conn.commit()
    return n


def record_correction(conn, review_id: int, corrected: str, reviewer: str) -> None:
    conn.execute(
        "UPDATE review_item SET status='corrected', corrected_value=?, reviewer=?, "
        "reviewed_at=? WHERE id=?",
        (corrected, reviewer, datetime.now(timezone.utc).isoformat(timespec="seconds"),
         review_id))
    conn.commit()
