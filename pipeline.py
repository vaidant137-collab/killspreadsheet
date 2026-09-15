"""
The whole pipeline, end to end, into the store.

    documents -> extract -> match -> normalise -> store -> review queue

Run:  python -m pipeline            (uses EXTRACTOR=fixture by default)
      EXTRACTOR=model python -m pipeline
"""

from __future__ import annotations

import json
import time

from config import DATA, DB_PATH, EXTRACTOR, REVIEW_THRESHOLD
from contracts.extraction import SourceDoc
from contracts.quote import GroundTruth, QuoteBasis, VendorLineQuote
from extract.base import get_extractor
from match.matcher import match_submission
from normalize.engine import default_assumptions, normalise_line
from store import repo


FORMAT_TO_PATH = {"photo": "image"}


def load_gt() -> GroundTruth:
    return GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))


def _as_quote(e) -> VendorLineQuote:
    return VendorLineQuote(
        line_no=e.line_no, rate=e.rate, currency=e.currency,
        basis=QuoteBasis(e.basis), refers_to_prior_contract=e.refers_to_prior_contract,
        excludes_sub_component=e.excludes_sub_component, tooling_inr=e.tooling_inr,
        tooling_amortised=e.tooling_amortised, note=e.note)


def apply_draft(gt: GroundTruth, draft) -> GroundTruth:
    """Fold the buyer's authored RFx into the ground truth before anything runs.

    This is what stops RFx authoring being theatre. The buyer's four real
    decisions land here, and everything downstream — normalisation, the gate,
    the allocator, the review queue — re-derives from them. Nothing is cached
    across an issue, because payment terms alone re-price all 139 cells.
    """
    gt = gt.model_copy(deep=True)
    if draft.line_nos:
        keep = set(draft.line_nos)
        gt.rfx.lines = [l for l in gt.rfx.lines if l.line_no in keep]
        for sub in gt.submissions:
            sub.line_quotes = [q for q in sub.line_quotes if q.line_no in keep]
    # A changed quantity is not cosmetic: it moves the line past or below a
    # vendor's minimum order and their slab boundaries, so the allocator has to
    # see it before it decides anything.
    for line_no, qty in (getattr(draft, "qty_overrides", None) or {}).items():
        for l in gt.rfx.lines:
            if l.line_no == int(line_no) and int(qty) > 0:
                l.annual_qty = int(qty)
    # A line nobody has bought before has no history and no quotes. It goes into
    # the schedule that is sent, and comes back empty in the comparison, which is
    # the honest result: it is a gap, not a zero, and the screen already knows
    # how to say that.
    for extra in (getattr(draft, "extra_lines", None) or []):
        try:
            from contracts.rfx import BoxStyle, Dimensions, RfxLine, Uom
            gt.rfx.lines.append(RfxLine(
                line_no=int(extra["line_no"]),
                code=str(extra.get("code") or f"NEW-{extra['line_no']}"),
                description=str(extra.get("description") or "New line"),
                style=BoxStyle(extra.get("style") or "sheet"),
                dims=Dimensions(length_mm=int(extra.get("length_mm") or 0),
                                width_mm=int(extra.get("width_mm") or 0)),
                annual_qty=int(extra.get("annual_qty") or 0),
                uom=Uom(extra.get("uom") or "piece"),
                introduced_this_year=True))
        except Exception:                                     # noqa: BLE001
            continue
    gt.rfx.lines.sort(key=lambda l: l.line_no)

    if draft.vendor_ids:
        want = set(draft.vendor_ids)
        gt.submissions = [s for s in gt.submissions if s.vendor.vendor_id in want]
    if draft.question_nos:
        keep_q = set(draft.question_nos)
        gt.rfx.questionnaire = [q for q in gt.rfx.questionnaire if q.q_no in keep_q]
        for sub in gt.submissions:
            sub.questionnaire = [a for a in sub.questionnaire if a.q_no in keep_q]
    # Gating is buyer policy. An empty gate list means the buyer chose to gate on
    # nothing, which is a real choice and not a missing value — so it is applied
    # as stated rather than defaulted back to the template.
    if draft.question_nos:
        gates = set(draft.gating_q_nos)
        for q in gt.rfx.questionnaire:
            q.gating = q.q_no in gates
    if draft.payment_terms_days is not None:
        gt.rfx.required_payment_terms = f"{draft.payment_terms_days} days from GRN"
    if draft.cost_of_capital_pct is not None:
        gt.rfx.cost_of_capital_pct = float(draft.cost_of_capital_pct)
    if draft.required_incoterm:
        gt.rfx.required_incoterm = draft.required_incoterm
    if draft.delivery_point:
        gt.rfx.delivery_point = draft.delivery_point
    if draft.buyer_org:
        gt.rfx.buyer_org = draft.buyer_org
    return gt


def _has_recordings() -> bool:
    """Is there a real recorded run on disk to replay?

    A path check rather than an import: pipeline.py is allowed to import any
    module, but there is nothing here worth importing extract/ for.
    """
    d = DATA / "extraction_runs"
    return d.is_dir() and any(d.glob("*.json"))


def run(*, fresh: bool = True, verbose: bool = True, mode: str | None = None,
        draft=None, on_progress=None, db_path=None, gt=None) -> dict:
    """Extract, match, normalise, allocate, store.

    `on_progress(event: dict)` is called as each vendor's reply is read. A
    procurement round is asynchronous — mail goes out, replies come back one at
    a time, and somebody wants to know where it has got to. The work here really
    is per vendor and really does take time, so the screen can show the true
    state of the round rather than a spinner with a story attached.
    """
    gt = gt if gt is not None else load_gt()
    if draft is not None:
        gt = apply_draft(gt, draft)
    lines = {l.line_no: l for l in gt.rfx.lines}
    mode = mode or EXTRACTOR

    # A deploy can be configured for `replay` and ship with nothing recorded.
    # That is not hypothetical: it is exactly what a build looks like after its
    # record run fails and falls back. Before this check, every re-run of the
    # pipeline through the API — which is what ISSUING an authored RFx does —
    # raised on the first document, so the whole second half of the product
    # 500'd on the live site while the first half looked perfectly healthy.
    #
    # Refusing is still the right behaviour FOR THE EXTRACTOR: replay returns a
    # recorded run verbatim or nothing at all. What to do about that refusal is
    # a composition decision, and this is the composition root.
    if mode == "replay" and not _has_recordings():
        if verbose:
            print("  replay was asked for and nothing is recorded — falling back "
                  "to the fixture path, and provenance will say so")
        mode = "fixture"

    # 1. extract, then 2. match — separately, so a bad parse cannot propagate
    #    into the arithmetic and a bad match is scored on its own terms.
    extracted, injections, degraded = [], [], []
    docs = {d["vendor_id"]: d for d in _doc_paths(gt)}
    for sub in gt.submissions:
        vid = sub.vendor.vendor_id
        # The vendor profile says how they replied; the extractor registry is
        # keyed by the parsing path. "photo" and "image" are the same thing
        # seen from the two ends.
        path = FORMAT_TO_PATH.get(sub.vendor.reply_format, sub.vendor.reply_format)
        doc = SourceDoc(doc_id=f"{vid}-quote", vendor_id=vid,
                        path=docs.get(vid, {}).get("path", ""),
                        kind=sub.vendor.reply_format, role="quote")
        t0 = time.monotonic()
        if on_progress:
            on_progress({"vendor_id": vid, "vendor": sub.vendor.name,
                         "state": "reading",
                         "format": sub.vendor.reply_format.value
                         if hasattr(sub.vendor.reply_format, "value")
                         else str(sub.vendor.reply_format)})
        try:
            raw = get_extractor(path, mode).extract(doc)
        except Exception as e:                                # noqa: BLE001
            # One document must not cost the other four. A model that loses its
            # shape on the photograph should not throw away four good parses and
            # send the whole build back to the fixture path — which is exactly
            # what happened on the first real deploy.
            #
            # The fallback is per document and it is RECORDED as a fallback, so
            # provenance reports "4 of 5 read by a model" rather than implying
            # five. A partial real run described accurately beats a complete one
            # described loosely.
            if mode in ("model", "record", "replay"):
                degraded.append((vid, f"{type(e).__name__}: {e}"))
                raw = get_extractor(path, "fixture").extract(doc)
            else:
                raise
        injections += [(vid, t) for t in raw.injection_attempts]
        matched = [m for m in match_submission(raw, gt) if m.line_no is not None]
        extracted += matched
        if on_progress:
            on_progress({"vendor_id": vid, "vendor": sub.vendor.name,
                         "state": "read", "lines": len(matched),
                         # How long this document actually took. On the replay
                         # path it is milliseconds; on a live model run it is
                         # where the minutes of a round go, and either way the
                         # number is measured rather than staged.
                         "ms": int((time.monotonic() - t0) * 1000),
                         "injection": bool(raw.injection_attempts),
                         "degraded": any(v == vid for v, _ in degraded)})

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
    out_db = db_path or DB_PATH
    conn = repo.init(out_db, fresh=fresh)
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

    if degraded:
        print("\n  documents that fell back to the fixture path:")
        for vid, why in degraded:
            print(f"    {vid:10s} {why[:110]}")

    if verbose:
        unres = sum(1 for n in normalised if n.state.value == "unresolved")
        print(f"\n  extractor        {mode}"
              + (f"  ({len(gt.submissions) - len(degraded)}/{len(gt.submissions)} "
                 f"read by the model)" if degraded else ""))
        print(f"  cells extracted  {len(extracted)}")
        print(f"  normalised       {len(normalised)}  ({unres} unresolved)")
        print(f"  review queue     {queued}  (threshold {REVIEW_THRESHOLD})")
        print(f"  qualified        {sum(1 for q in qual.values() if q.qualified)}/"
              f"{len(qual)} vendors")
        print(f"  splits evaluated {len(allocs)}  ({len(feasible)} feasible)")
        if feasible:
            b = feasible[0]
            print(f"  best feasible    {b.strategy}  Rs {b.total_inr:,.0f}")
        print(f"  database         {out_db.name}\n")

    return {"extracted": len(extracted), "normalised": len(normalised),
            "queued": queued, "allocations": allocs, "conn": conn,
            "degraded": degraded}


def _doc_paths(gt: GroundTruth | None = None) -> list[dict]:
    """Where each vendor's quotation actually lives, for the model-backed paths."""
    gen = DATA / "generated"
    want = {"xlsx": ".xlsx", "pdf": ".pdf", "docx": ".docx",
            "photo": ".jpg", "email": ".eml"}
    out = []
    for sub in (gt or load_gt()).submissions:
        vid, ext = sub.vendor.vendor_id, want[sub.vendor.reply_format]
        hit = next((p for p in sorted(gen.glob(f"{vid}*{ext}"))
                    if "questionnaire" not in p.name), None)
        if hit:
            out.append({"vendor_id": vid, "path": str(hit.relative_to(DATA.parent))})
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["fixture", "replay", "model", "record"],
                    help="fixture: no key needed · replay: a recorded real run · "
                         "model: call now · record: call now and save it")
    a = ap.parse_args()
    run(mode=a.extractor)


def apply_clarifications(gt, vendor_ids: list[str]):
    """Fold round two into the ground truth, for the vendors who answered.

    The buyer wrote back, the vendor replied, and what came back changes real
    things: a box weight turns six unpriceable cells into prices, a current
    certificate puts a disqualified vendor back in contention, a revised minimum
    order unblocks lines that were never buyable at the rate quoted.

    Applied here rather than in the store because everything downstream —
    normalisation, the gate, the allocator, the review queue — has to re-derive
    from it. A clarification that only updated a display would be the same
    failure as a review queue that does not change the answer.
    """
    gt = gt.model_copy(deep=True)
    want = set(vendor_ids)
    applied: list[dict] = []
    for c in gt.clarifications:
        if c.vendor_id not in want:
            continue
        changed: list[str] = []

        for line_no, grams in (c.unit_weights_g or {}).items():
            for l in gt.rfx.lines:
                if l.line_no == int(line_no):
                    l.unit_weight_g = float(grams)
                    changed.append(f"line {l.line_no} weight {grams:.0f} g")

        sub = next((s for s in gt.submissions
                    if s.vendor.vendor_id == c.vendor_id), None)
        if sub is not None:
            for a in c.questionnaire:
                prev = next((x for x in sub.questionnaire if x.q_no == a.q_no), None)
                if prev is not None:
                    sub.questionnaire.remove(prev)
                sub.questionnaire.append(a)
                changed.append(f"question {a.q_no} answered again")
            sub.questionnaire.sort(key=lambda x: x.q_no)

            for att in (c.attachments or []):
                # Replace the document of the same kind rather than appending:
                # the whole point is that the expired one no longer governs.
                sub.attachments = [x for x in sub.attachments if x.kind != att.kind]
                sub.attachments.append(att)
                changed.append(f"{att.kind} document replaced "
                               f"(valid to {att.valid_until})")

            if c.moq_pieces is not None:
                changed.append(f"minimum order {sub.vendor.moq_pieces:,} "
                               f"→ {c.moq_pieces:,}")
                sub.vendor.moq_pieces = c.moq_pieces

            for q in c.line_quotes:
                sub.line_quotes = [x for x in sub.line_quotes
                                   if x.line_no != q.line_no]
                sub.line_quotes.append(q)
                changed.append(f"line {q.line_no} now priced")
            sub.line_quotes.sort(key=lambda x: x.line_no)

        applied.append({"vendor_id": c.vendor_id, "changed": changed,
                        "declined": c.declined, "received_at": c.received_at})
    return gt, applied
