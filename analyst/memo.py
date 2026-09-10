"""
The award memo — the artifact that actually leaves the tool.

The comparison is a means. The thing a procurement team needs six months later,
when Finance asks why this vendor at this price, is the decision record: what
was awarded, on what basis, under which assumptions, with which cells verified
by a human and by whom.

Most tools in this space ship the table and leave the buyer to write the memo in
Word, which is exactly why the spreadsheet survives. Ending the flow here is the
small move that makes the tool the system of record rather than a step on the
way to one.
"""

from __future__ import annotations

import json
from datetime import date

from contracts.normalized import Allocation


def build(conn, alloc: Allocation) -> str:
    rfx = dict(conn.execute("SELECT * FROM rfx LIMIT 1").fetchone())
    vendors = {r["vendor_id"]: dict(r) for r in conn.execute(
        "SELECT vendor_id,name,city,qualified,disqualified_because,payment_days,"
        "validity_days,incoterm FROM vendor").fetchall()}
    assumptions = [dict(r) for r in conn.execute(
        "SELECT * FROM assumption ORDER BY key").fetchall()]
    unresolved = [dict(r) for r in conn.execute(
        "SELECT vendor_id,line_no,missing_fact FROM normalised_line "
        "WHERE state='unresolved' ORDER BY vendor_id,line_no").fetchall()]
    reviewed = [dict(r) for r in conn.execute(
        "SELECT vendor_id,line_no,field,status,corrected_value,reviewer,reviewed_at "
        "FROM review_item WHERE status!='open' ORDER BY reviewed_at").fetchall()]
    open_reviews = conn.execute(
        "SELECT COUNT(*) c FROM review_item WHERE status='open'").fetchone()["c"]
    contradictions = [dict(r) for r in conn.execute(
        "SELECT vendor_id,question,answer,contradiction_note FROM questionnaire_answer "
        "WHERE contradicted_by_evidence=1").fetchall()]

    L: list[str] = []
    A = L.append
    A(f"# Award recommendation — {rfx['title']}")
    A("")
    A(f"**{rfx['rfx_id']}** · {rfx['buyer_org']} · prepared {date.today():%d %B %Y}")
    A("")
    A("## Recommendation")
    A("")
    names = ", ".join(vendors[v]["name"] for v in alloc.vendors_used)
    A(f"Award to **{names}** on the split below, at a total landed cost of "
      f"**₹{alloc.total_inr:,.0f}** for the year "
      f"(₹{alloc.line_value_inr:,.0f} of line value plus ₹{alloc.freight_inr:,.0f} "
      f"of inbound freight across {len(alloc.vendors_used)} "
      f"{'lane' if len(alloc.vendors_used) == 1 else 'lanes'}).")
    A("")
    A("## Basis of comparison")
    A("")
    A(f"All rates are stated as **landed cost per buyer unit, pre-tax**, adjusted to "
      f"the {rfx['required_payment_terms']} the RFx asked for. No vendor quoted on "
      f"that basis; every figure below is derived, and the derivations are listed.")
    A("")
    for a in assumptions:
        A(f"- **{a['label']}**: {a['value']}{' ' + a['unit'] if a['unit'] else ''} "
          f"— {a['source']}")
    A("")
    A("## Award by line")
    A("")
    A("| Line | Vendor | ₹ / unit | Annual qty | Annual ₹ |")
    A("|---|---|---:|---:|---:|")
    for aw in alloc.awards:
        if aw.vendor_id:
            A(f"| {aw.line_no} | {vendors[aw.vendor_id]['name']} | {aw.unit_inr:,.2f} "
              f"| {aw.annual_qty:,} | {aw.annual_inr:,.0f} |")
        else:
            A(f"| {aw.line_no} | — | — | {aw.annual_qty:,} | **not awarded** |")
    A("")

    if alloc.caveats:
        A("## What this split costs")
        A("")
        for c in alloc.caveats:
            A(f"- {c}")
        A("")
    if alloc.violations:
        A("## Constraints breached")
        A("")
        for v in alloc.violations:
            A(f"- {v}")
        A("")

    dq = [v for v in vendors.values() if not v["qualified"]]
    if dq:
        A("## Vendors excluded")
        A("")
        for v in dq:
            reasons = json.loads(v["disqualified_because"] or "[]")
            A(f"- **{v['name']}** — {'; '.join(reasons)}")
        A("")
    if contradictions:
        A("## Evidence that contradicts a stated answer")
        A("")
        for c in contradictions:
            A(f"- **{vendors[c['vendor_id']]['name']}** answered “{c['answer']}”. "
              f"{c['contradiction_note']}")
        A("")

    A("## What this record does not establish")
    A("")
    if unresolved:
        A(f"{len(unresolved)} cells could not be derived and were left empty rather than "
          f"estimated. They are excluded from the totals above:")
        A("")
        for u in unresolved:
            A(f"- {vendors[u['vendor_id']]['name']}, line {u['line_no']} — "
              f"needs {u['missing_fact']}")
        A("")
    A(f"{len(reviewed)} cells were reviewed by a human; {open_reviews} remain in the "
      f"queue and were accepted at the extractor's confidence.")
    A("")
    if reviewed:
        A("| Vendor | Line | Field | Outcome | By | When |")
        A("|---|---|---|---|---|---|")
        for r in reviewed:
            A(f"| {r['vendor_id']} | {r['line_no']} | {r['field']} | {r['status']}"
              f"{' → ' + r['corrected_value'] if r['corrected_value'] else ''} "
              f"| {r['reviewer']} | {r['reviewed_at']} |")
        A("")
    A("---")
    A("")
    A("Generated from the comparison database. Every figure traces to an extracted "
      "value and a stated assumption; nothing here was asserted without a source.")
    return "\n".join(L)
