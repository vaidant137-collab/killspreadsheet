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

    The gate is deliberately shallow and deliberately visible: ISO 9001 valid,
    and no more than two quality escapes in 24 months. It is a buyer policy, not
    a property of the software, and the buyer changes it in the conversation.

    The one piece of real work here: an ISO answer is checked against the
    attached certificate. Nova answered "Yes" in good faith; the certificate
    they attached expired in March. Nobody lied — the renewal is late at the
    plant — and only reading the attachment catches it.
    """
    out: dict[str, VendorTotals] = {}
    for sub in gt.submissions:
        reasons: list[str] = []
        ans = {a.q_no: a for a in sub.questionnaire}

        iso = ans.get(1)
        claims_iso = iso and ("yes" in iso.answer.lower() or "iso 9001" in iso.answer.lower())
        if not claims_iso:
            reasons.append("Not ISO 9001 certified")
        for att in sub.attachments:
            if att.kind == "iso9001" and att.valid_until:
                if date.fromisoformat(att.valid_until) < TODAY:
                    reasons.append(
                        f"ISO 9001 certificate expired {att.valid_until}, contradicting "
                        f"their 'Yes' at question 1")

        try:
            # "1 (minor - print registration, Aug 2025)" is one escape, not 12,025.
            # Take the FIRST integer, not every digit in the sentence.
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
