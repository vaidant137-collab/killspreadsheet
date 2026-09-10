"""
The whole pipeline, end to end, into the store.

    documents -> extract -> match -> normalise -> store -> review queue

Run:  python -m pipeline            (uses EXTRACTOR=fixture by default)
      EXTRACTOR=model python -m pipeline
"""

from __future__ import annotations

import json

from config import DATA, DB_PATH, EXTRACTOR, REVIEW_THRESHOLD
from contracts.extraction import SourceDoc
from contracts.quote import GroundTruth, QuoteBasis, VendorLineQuote
from extract.base import get_extractor
from match.matcher import match_submission
from normalize.engine import default_assumptions, normalise_line
from store import repo


def load_gt() -> GroundTruth:
    return GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))


def _as_quote(e) -> VendorLineQuote:
    return VendorLineQuote(
        line_no=e.line_no, rate=e.rate, currency=e.currency,
        basis=QuoteBasis(e.basis), refers_to_prior_contract=e.refers_to_prior_contract,
        excludes_sub_component=e.excludes_sub_component, tooling_inr=e.tooling_inr,
        tooling_amortised=e.tooling_amortised, note=e.note)


def run(*, fresh: bool = True, verbose: bool = True) -> dict:
    gt = load_gt()
    lines = {l.line_no: l for l in gt.rfx.lines}
    ex = get_extractor("fixture")

    # 1. extract, then 2. match — separately, so a bad parse cannot propagate
    #    into the arithmetic and a bad match is scored on its own terms.
    extracted, injections = [], []
    for sub in gt.submissions:
        vid = sub.vendor.vendor_id
        raw = ex.extract(SourceDoc(doc_id=f"{vid}-quote", vendor_id=vid, path="",
                                   kind=sub.vendor.reply_format, role="quote"))
        injections += [(vid, t) for t in raw.injection_attempts]
        extracted += [m for m in match_submission(raw, gt) if m.line_no is not None]

    # 3. normalise — deterministic, no model
    from allocate.subsets import allocate, qualify
    qual = qualify(gt)
    per_vendor_units: dict[str, float] = {}
    for e in extracted:
        per_vendor_units[e.vendor_id] = per_vendor_units.get(e.vendor_id, 0) + \
            lines[e.line_no].annual_qty

    profiles = {s.vendor.vendor_id: s.vendor for s in gt.submissions}
    normalised = []
    for e in extracted:
        n = normalise_line(_as_quote(e), lines[e.line_no], profiles[e.vendor_id],
                           gt, per_vendor_units[e.vendor_id] or 1)
        n.extraction_confidence = e.extraction_confidence
        n.match_confidence = e.match_confidence
        n.evidence_ref = e.evidence.evidence_id if e.evidence else None
        normalised.append(n)

    # 4. store
    conn = repo.init(DB_PATH, fresh=fresh)
    repo.load_rfx(conn, gt)
    repo.load_vendors(conn, gt, qual)
    repo.load_documents(conn, gt)
    repo.load_questionnaire(conn, gt)
    repo.load_assumptions(conn, default_assumptions(gt))
    repo.load_quotes(conn, gt, extracted)
    repo.load_normalised(conn, normalised)
    queued = repo.queue_reviews(conn, normalised, REVIEW_THRESHOLD)
    for vid, txt in injections:
        conn.execute("INSERT INTO injection_attempt (vendor_id, excerpt) VALUES (?,?)",
                     (vid, txt))
    conn.commit()

    allocs = allocate(gt, normalised)
    feasible = [a for a in allocs if a.feasible]

    if verbose:
        unres = sum(1 for n in normalised if n.state.value == "unresolved")
        print(f"\n  extractor        {EXTRACTOR}")
        print(f"  cells extracted  {len(extracted)}")
        print(f"  normalised       {len(normalised)}  ({unres} unresolved)")
        print(f"  review queue     {queued}  (threshold {REVIEW_THRESHOLD})")
        print(f"  qualified        {sum(1 for q in qual.values() if q.qualified)}/"
              f"{len(qual)} vendors")
        print(f"  splits evaluated {len(allocs)}  ({len(feasible)} feasible)")
        if feasible:
            b = feasible[0]
            print(f"  best feasible    {b.strategy}  Rs {b.total_inr:,.0f}")
        print(f"  database         {DB_PATH.name}\n")

    return {"extracted": len(extracted), "normalised": len(normalised),
            "queued": queued, "allocations": allocs, "conn": conn}


if __name__ == "__main__":
    run()
