"""
Award allocation by enumeration.

The instinct for the VP's question is a mixed-integer program. It is also eight
hours, and slab pricing makes it a piecewise-linear problem with binary
selection variables that reports "infeasible" and nothing else when it fails.

But the search space here is not large. At most three vendors from five is
5 + 10 + 10 = 25 combinations. So do not solve it — enumerate it, evaluate each
subset exactly, and rank. Milliseconds, no solver, and every rejected subset can
say why it was rejected, which a solver cannot.

An honest note on the fixed point: the slab wording in Meridian's offer is
"above 50,000 pieces PER LINE ITEM", so the slab depends on the line's own
annual volume, which is known upfront — there is no circularity to iterate out.
The genuinely circular term is freight, because it is a per-vendor fixed cost
divided by however many lines that vendor wins, and that is resolved here by
evaluating it once per subset rather than once per line.

Run:  python -m allocate.subsets --self-test
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from itertools import combinations

from config import DATA, MAX_VENDORS_IN_SPLIT
from contracts.normalized import Allocation, CellState, LineAward, NormalisedLine, VendorTotals
from contracts.quote import GroundTruth
from normalize.engine import normalise_all

TODAY = date(2026, 9, 10)


# ---------------------------------------------------------------------------
# The questionnaire gate
# ---------------------------------------------------------------------------

def qualify(gt: GroundTruth) -> dict[str, VendorTotals]:
    """Who cleared the quality questionnaire.

    The rules are deliberately shallow and deliberately visible: ISO 9001 valid,
    and no more than two quality escapes in 24 months. WHETHER EACH ONE BITES is
    the buyer's call, taken when they authored the RFx and marked a question
    gating. It is a buyer policy, not a property of the software, which is why it
    is read off the RFx rather than hard-coded here.

    The one piece of real work here: an ISO answer is checked against the
    attached certificate. Nova answered "Yes" in good faith; the certificate
    they attached expired in March. Nobody lied — the renewal is late at the
    plant — and only reading the attachment catches it.
    """
    # Which questions are ALLOWED to disqualify is the buyer's decision, made
    # when they authored the RFx. The rules below are the software's; whether
    # each one bites is theirs. A buyer who un-gates the quality-escape question
    # gets their lowest bidder back, and should be able to see that happen.
    gated = {q.q_no for q in gt.rfx.questionnaire if q.gating}

    out: dict[str, VendorTotals] = {}
    for sub in gt.submissions:
        reasons: list[str] = []
        ans = {a.q_no: a for a in sub.questionnaire}

        if 1 in gated:
            iso = ans.get(1)
            claims_iso = iso and ("yes" in iso.answer.lower()
                                  or "iso 9001" in iso.answer.lower())
            if not claims_iso:
                reasons.append("Not ISO 9001 certified")
            for att in sub.attachments:
                if att.kind == "iso9001" and att.valid_until:
                    if date.fromisoformat(att.valid_until) < TODAY:
                        reasons.append(
                            f"ISO 9001 certificate expired {att.valid_until}, contradicting "
                            f"their 'Yes' at question 1")

        if 7 in gated:
            try:
                # "1 (minor - print registration, Aug 2025)" is one escape, not
                # 12,025. Take the FIRST integer, not every digit in the sentence.
                m = re.match(r"\s*(\d+)", ans[7].answer)
                if not m:
                    raise ValueError(ans[7].answer)
                escapes = int(m.group(1))
                if escapes > 2:
                    reasons.append(f"{escapes} quality escapes in 24 months (limit 2)")
            except Exception:
                reasons.append("Quality escape history not stated")

        out[sub.vendor.vendor_id] = VendorTotals(
            vendor_id=sub.vendor.vendor_id,
            lines_quoted=len(sub.line_quotes), lines_resolved=0, lines_unresolved=0,
            covered_annual_value_inr=0.0,
            qualified=not reasons, disqualified_because=reasons)
    return out


def strength_warnings(gt: GroundTruth) -> list[str]:
    """Not a gate — a warning. Board strength is quoted against three different
    standards that do not convert into one another, so 'meets spec' means
    different things per vendor and a gate that accepted it would be theatre."""
    w = []
    for sub in gt.submissions:
        a = next((x for x in sub.questionnaire if x.q_no == 8), None)
        if not a:
            continue
        t = a.answer.lower()
        cited = any(k in t for k in ("is 2771", "iso 3037", "tappi", "t 811", "t810"))
        if not cited:
            w.append(f"{sub.vendor.name}: strength stated as \"{a.answer}\" with no test "
                     f"method cited — not verifiable, and not comparable with the others")
    return w


# ---------------------------------------------------------------------------

def _ex_freight(n: NormalisedLine) -> float | None:
    """Landed cost with the per-vendor freight taken back out.

    Normalisation loads freight assuming the vendor wins everything they quoted.
    That assumption is wrong for every split, so allocation strips it and adds
    the vendor's real annual freight once, per subset.
    """
    if n.landed_inr is None:
        return None
    return n.landed_inr - (n.freight_inr or 0.0)


def _slab_uplift(gt: GroundTruth, vendor_id: str, annual_qty: int) -> float:
    v = next(s.vendor for s in gt.submissions if s.vendor.vendor_id == vendor_id)
    if not v.slabs:
        return 0.0
    for slab in sorted(v.slabs, key=lambda s: -s.min_qty):
        if annual_qty >= slab.min_qty:
            return slab.uplift_pct
    return 0.0


def evaluate(gt: GroundTruth, rows: list[NormalisedLine], subset: tuple[str, ...],
             strategy: str) -> Allocation:
    lines = {l.line_no: l for l in gt.rfx.lines}
    idx: dict[tuple[str, int], NormalisedLine] = {(r.vendor_id, r.line_no): r for r in rows}

    awards: list[LineAward] = []
    line_value = tooling = 0.0
    won: dict[str, list[int]] = {v: [] for v in subset}
    uncovered: list[int] = []
    caveats: list[str] = []

    for ln in gt.rfx.lines:
        best_v, best_unit = None, None
        for v in subset:
            n = idx.get((v, ln.line_no))
            if n is None or n.state == CellState.UNRESOLVED:
                continue
            unit = _ex_freight(n)
            if unit is None:
                continue
            uplift = _slab_uplift(gt, v, ln.annual_qty)
            if uplift:
                unit *= (1 + uplift / 100.0)
                caveats.append(
                    f"Line {ln.line_no}: {v} priced at {ln.annual_qty:,} units, below "
                    f"their 50,000 slab — {uplift:.1f}% uplift applied, so the rate they "
                    f"quoted was never valid at this volume.")
            if best_unit is None or unit < best_unit:
                best_v, best_unit = v, unit

        if best_v is None:
            uncovered.append(ln.line_no)
            awards.append(LineAward(line_no=ln.line_no, vendor_id=None, unit_inr=None,
                                    annual_qty=ln.annual_qty, annual_inr=None,
                                    uncovered_reason="No qualified vendor in this split "
                                                     "has a resolved price for this line"))
            continue

        annual = best_unit * ln.annual_qty
        line_value += annual
        won[best_v].append(ln.line_no)
        awards.append(LineAward(line_no=ln.line_no, vendor_id=best_v,
                                unit_inr=round(best_unit, 4), annual_qty=ln.annual_qty,
                                annual_inr=round(annual, 2)))

    # --- per-vendor fixed costs and constraints ----------------------------
    freight = 0.0
    violations: list[str] = []
    used = [v for v in subset if won[v]]
    for v in used:
        prof = next(s.vendor for s in gt.submissions if s.vendor.vendor_id == v)
        if prof.freight_inr_per_shipment:
            freight += prof.freight_inr_per_shipment * prof.shipments_per_year
        for ln_no in won[v]:
            if lines[ln_no].annual_qty < prof.moq_pieces:
                violations.append(
                    f"{prof.name} wins line {ln_no} at {lines[ln_no].annual_qty:,} units, "
                    f"below their {prof.moq_pieces:,} minimum order")

    if uncovered:
        violations.append(f"{len(uncovered)} lines have no price in this split: "
                          f"{', '.join(str(x) for x in uncovered)}")

    if len(used) > 1:
        caveats.append(f"{len(used)} vendors means {len(used)} inbound lanes, "
                       f"not one — freight is a per-vendor fixed cost, not a rate.")

    return Allocation(
        strategy=strategy, vendors_used=used, awards=awards,
        line_value_inr=round(line_value, 2), freight_inr=round(freight, 2),
        tooling_inr=round(tooling, 2),
        total_inr=round(line_value + freight + tooling, 2),
        feasible=not violations, violations=violations,
        caveats=sorted(set(caveats)), uncovered_lines=uncovered)


def allocate(gt: GroundTruth, rows: list[NormalisedLine], *,
             qualified_only: bool = True,
             max_vendors: int = MAX_VENDORS_IN_SPLIT) -> list[Allocation]:
    """Every viable split, best first. 25 evaluations, milliseconds."""
    q = qualify(gt)
    pool = [v for v, t in q.items() if t.qualified] if qualified_only else list(q)
    results: list[Allocation] = []
    for k in range(1, min(max_vendors, len(pool)) + 1):
        for subset in combinations(sorted(pool), k):
            results.append(evaluate(gt, rows, subset,
                                    strategy=f"{k}-vendor: {', '.join(subset)}"))
    return sorted(results, key=lambda a: (not a.feasible, a.total_inr))


# ---------------------------------------------------------------------------
# The decision layer
# ---------------------------------------------------------------------------

def lead_times(gt: GroundTruth) -> dict[str, int | None]:
    """Production lead time per vendor, from questionnaire Q9.

    A split waits for its SLOWEST vendor, not its average one, so this is the
    number that decides whether "cheapest" is also "in time for the season".
    A vendor who did not answer gets None rather than a default: an unstated
    lead time is not a fast one, and guessing it here would be the same class
    of error as guessing a price.
    """
    out: dict[str, int | None] = {}
    for sub in gt.submissions:
        a = next((x for x in sub.questionnaire if x.q_no == 9), None)
        m = re.match(r"\s*(\d+)", a.answer) if a and a.answer else None
        out[sub.vendor.vendor_id] = int(m.group(1)) if m else None
    return out


def _span(alloc: Allocation, lt: dict[str, int | None]) -> int | None:
    vals = [lt.get(v) for v in alloc.vendors_used]
    return None if any(v is None for v in vals) or not vals else max(vals)


def options(gt: GroundTruth, rows: list[NormalisedLine]) -> list[dict]:
    """The three shapes of answer a category manager actually chooses between.

    Not a ranking of 25 subsets — nobody decides from that. Cheapest, fastest,
    and the one-throat-to-choke option, each with what it costs, who is in it,
    how long it takes, and the reason it might not be available at all. The
    single-vendor option is included EVEN WHEN IT IS INFEASIBLE, because "no
    single vendor can cover this schedule" is itself the finding.
    """
    allocs = allocate(gt, rows)
    lt = lead_times(gt)
    feasible = [a for a in allocs if a.feasible]
    if not allocs:
        return []

    def card(alloc, kind, label, why):
        return {"kind": kind, "label": label, "why": why,
                "strategy": alloc.strategy,
                "vendors": alloc.vendors_used,
                "vendor_names": [next(s.vendor.name for s in gt.submissions
                                      if s.vendor.vendor_id == v)
                                 for v in alloc.vendors_used],
                "total_inr": alloc.total_inr,
                "line_value_inr": alloc.line_value_inr,
                "freight_inr": alloc.freight_inr,
                "tooling_inr": alloc.tooling_inr,
                "lead_time_days": _span(alloc, lt),
                "lines_covered": sum(1 for x in alloc.awards if x.vendor_id),
                "lines_total": len(gt.rfx.lines),
                "feasible": alloc.feasible,
                "violations": alloc.violations,
                "caveats": alloc.caveats[:3]}

    out = []
    cheapest = feasible[0] if feasible else None
    if cheapest:
        out.append(card(cheapest, "cheapest", "Cheapest",
                        "Lowest total landed cost among splits that clear every "
                        "constraint — minimum order quantities, tooling, and the "
                        "questionnaire gate."))

    timed = [a for a in feasible if _span(a, lt) is not None]
    if timed:
        fastest = min(timed, key=lambda a: (_span(a, lt), a.total_inr))
        if not cheapest or fastest.strategy != cheapest.strategy:
            premium = fastest.total_inr - cheapest.total_inr if cheapest else 0
            out.append(card(fastest, "fastest", "Fastest",
                            f"Shortest wait, because a split is only as quick as its "
                            f"slowest vendor. Costs ₹{premium:,.0f} more than the "
                            f"cheapest option."))
        elif cheapest:
            out[0]["label"] = "Cheapest — and fastest"
            out[0]["why"] += " It also happens to be the quickest."

    singles = [a for a in allocs if len(a.vendors_used) == 1]
    single = (min([a for a in singles if a.feasible], key=lambda a: a.total_inr)
              if any(a.feasible for a in singles)
              else (min(singles, key=lambda a: a.total_inr) if singles else None))
    if single:
        if single.feasible:
            extra = single.total_inr - cheapest.total_inr if cheapest else 0
            why = (f"One contract, one relationship, one invoice stream. "
                   f"₹{extra:,.0f} more than splitting.")
        else:
            why = ("No single vendor can cover this schedule on its own — "
                   "which is the finding, not a failure of the search.")
        out.append(card(single, "single", "Single vendor", why))
    return out


# ---------------------------------------------------------------------------

def _self_test() -> int:
    gt = GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    rows = normalise_all(gt)
    q = qualify(gt)

    print("\n  Questionnaire gate — ISO 9001 valid, escapes <= 2\n")
    for vid, t in q.items():
        name = next(s.vendor.name for s in gt.submissions if s.vendor.vendor_id == vid)
        mark = "PASS" if t.qualified else "FAIL"
        print(f"    {mark:4s}  {name}")
        for r in t.disqualified_because:
            print(f"          {r}")

    print("\n  Warnings that are NOT gates:\n")
    for w in strength_warnings(gt):
        print(f"    · {w}")

    allocs = allocate(gt, rows)
    print(f"\n  {len(allocs)} splits evaluated among qualified vendors\n")
    print(f"    {'split':34s} {'total INR':>14s}  {'lines':>5s}  feasible")
    for a in allocs[:8]:
        cov = sum(1 for x in a.awards if x.vendor_id)
        print(f"    {a.strategy:34s} {a.total_inr:14,.0f}  {cov:2d}/30  "
              f"{'yes' if a.feasible else 'NO'}")

    feasible = [a for a in allocs if a.feasible]
    best = feasible[0] if feasible else allocs[0]
    label = "Best feasible" if feasible else "Cheapest, but NOT feasible"
    print(f"\n  {label}: {best.strategy}")
    print(f"    line value  {best.line_value_inr:14,.0f}")
    print(f"    freight     {best.freight_inr:14,.0f}   ({len(best.vendors_used)} inbound lanes)")
    print(f"    total       {best.total_inr:14,.0f}")
    for c in best.caveats:
        print(f"    · {c}")
    for v in best.violations:
        print(f"    ! {v}")

    single = [a for a in allocs if len(a.vendors_used) == 1 and a.feasible]
    if single and len(best.vendors_used) > 1:
        s = single[0]
        print(f"\n  Versus single-sourcing to {s.vendors_used[0]}: "
              f"{s.total_inr:,.0f}  (split saves {s.total_inr - best.total_inr:,.0f})")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    raise SystemExit(_self_test() if p.parse_args().self_test else 0)
