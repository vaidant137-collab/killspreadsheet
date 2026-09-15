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

        # Any OTHER gating question is a plain yes/no policy: "No" disqualifies.
        # Q1 and Q7 get bespoke rules above because they are the two that read an
        # attachment and parse a number. Without this branch, marking FSC or
        # BRCGS as gating did nothing at all — the buyer set a policy and the
        # software silently ignored it, which is worse than refusing to offer it.
        for q in gt.rfx.questionnaire:
            if q.q_no in (1, 7) or q.q_no not in gated:
                continue
            a = ans.get(q.q_no)
            if a is None:
                reasons.append(f"No answer to Q{q.q_no} ({q.question[:48]})")
            elif a.answer.strip().lower().startswith("no"):
                reasons.append(f"Q{q.q_no}: answered No — {q.question[:56]}")

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

    # Lines NOBODY priced — a line the buyer added this year, or one every
    # vendor left blank. It is missing from every split equally, so counting it
    # against this one makes all 25 infeasible and the buyer is told their own
    # new line broke the tender. It is a coverage caveat, not a violation.
    nobody: set[int] = {
        ln.line_no for ln in gt.rfx.lines
        if not any((idx.get((s_.vendor.vendor_id, ln.line_no)) is not None
                    and idx[(s_.vendor.vendor_id, ln.line_no)].state
                    != CellState.UNRESOLVED
                    and _ex_freight(idx[(s_.vendor.vendor_id, ln.line_no)]) is not None)
                   for s_ in gt.submissions)}

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
                                    uncovered_reason=(
                                        "Nobody quoted this line at all"
                                        if ln.line_no in nobody else
                                        "No qualified vendor in this split "
                                        "has a resolved price for this line")))
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

    blind = [n for n in uncovered if n in nobody]
    losable = [n for n in uncovered if n not in nobody]
    if losable:
        violations.append(f"{len(losable)} lines have no price in this split: "
                          f"{', '.join(str(x) for x in losable)} — somebody else "
                          f"quoted them")
    if blind:
        caveats.append(f"{len(blind)} line{'' if len(blind) == 1 else 's'} "
                       f"({', '.join(str(x) for x in blind)}) "
                       f"{'is' if len(blind) == 1 else 'are'} unpriced by every "
                       f"vendor, so {'it sits' if len(blind) == 1 else 'they sit'} "
                       f"outside this split and every other one. Not counted in "
                       f"the total.")

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
# Consequence preview — what a choice COSTS, before it is made
# ---------------------------------------------------------------------------

def gate_preview(gt: GroundTruth) -> list[dict]:
    """For each questionnaire question: who would it disqualify, on today's data.

    This is the difference between a settings screen and a decision. "Gate on
    FSC chain of custody" is not a preference — it removes three of five
    vendors, and one of the two it leaves is the most expensive in the set. A
    buyer should read that on the option before clicking it, not discover it
    afterwards when the comparison comes back thin.

    Computed by running the real gate with that question alone, so the line is a
    measurement rather than a guess. A model writing these from memory would be
    the worst version of this feature.
    """
    out = []
    for q in gt.rfx.questionnaire:
        probe = gt.model_copy(deep=True)
        for x in probe.rfx.questionnaire:
            x.gating = (x.q_no == q.q_no)
        res = qualify(probe)
        removed = [v for v, t in res.items() if not t.qualified]
        names = {s.vendor.vendor_id: s.vendor.name for s in gt.submissions}
        out.append({
            "q_no": q.q_no, "question": q.question,
            "gating_now": q.gating,
            "removes": removed,
            "removes_names": [names.get(v, v) for v in removed],
            "consequence": ("removes nobody today" if not removed
                            else f"removes {', '.join(names.get(v, v).split()[0] for v in removed)}"
                            if len(removed) < len(res)
                            else "removes every vendor — nobody would qualify"),
        })
    return out


def terms_preview(gt: GroundTruth, candidates=(30, 45, 60, 90)) -> list[dict]:
    """What each candidate payment term does to who looks cheapest.

    Terms are the least obviously consequential field on an RFx and one of the
    most consequential in fact: every rate is NPV-adjusted to them, so the term
    the buyer picks partly decides the winner. Showing that as four numbers is
    more honest than a paragraph explaining that it matters.
    """
    names = {s.vendor.vendor_id: s.vendor.name for s in gt.submissions}
    out = []
    for days in candidates:
        probe = gt.model_copy(deep=True)
        probe.rfx.required_payment_terms = f"{days} days from GRN"
        rows = normalise_all(probe)
        totals: dict[str, float] = {}
        for r in rows:
            if r.landed_inr is not None:
                line = next((l for l in probe.rfx.lines if l.line_no == r.line_no), None)
                if line:
                    totals[r.vendor_id] = totals.get(r.vendor_id, 0.0) + \
                        r.landed_inr * line.annual_qty
        best = min(totals, key=totals.get) if totals else None
        out.append({"days": days, "cheapest": best,
                    "cheapest_name": names.get(best, best),
                    "total_inr": round(totals.get(best, 0.0), 2),
                    "totals": {k: round(v, 2) for k, v in totals.items()}})

    # "Who is cheapest" often does not change across terms, which makes it a
    # useless thing to put on the option. What DOES change is how much each
    # vendor's own terms are worth to them — a vendor quoting 90 days gains
    # against a 30-day tender and loses against a 90-day one. Name the biggest
    # mover against the 45-day baseline, because that is the consequence.
    base = next((r for r in out if r["days"] == 45), out[0])
    for r in out:
        moves = {v: r["totals"].get(v, 0) - base["totals"].get(v, 0)
                 for v in base["totals"]}
        big = max(moves, key=lambda v: abs(moves[v])) if moves else None
        delta = moves.get(big, 0.0) if big else 0.0
        if r["days"] == base["days"]:
            r["consequence"] = "the baseline — matches your FY26 contract"
        elif big is None or abs(delta) < 1:
            r["consequence"] = "moves nobody materially"
        else:
            direction = "costs" if delta > 0 else "saves"
            r["consequence"] = (f"{names.get(big, big).split()[0]} {direction} you "
                                f"INR {abs(delta):,.0f} a year against 45 days")
        r["moves_most"] = big
        r["moves_most_inr"] = round(delta, 2)
    return out


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
    if not timed:
        # Not a failure of the search. The buyer's own questionnaire decided
        # this: lead time is question 9, and if they did not send question 9
        # nobody stated one, so nothing here can be ranked on speed. Saying
        # which of their decisions removed the option is more useful than
        # quietly showing two cards under a heading that promises three.
        asked = {q.q_no for q in gt.rfx.questionnaire}
        out.append({"kind": "fastest_unavailable", "label": "Fastest",
                    "unavailable": True,
                    "why": ("Nobody stated a lead time, so nothing here can be "
                            "ranked on speed." + (
                                " Question 9 asks for it and this RFx did not "
                                "include it — add it and re-issue to get this "
                                "option back." if 9 not in asked else
                                " Question 9 asked for it and no vendor answered."))})
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

    # --- the invariant that matters most, and the easiest to lose -----------
    # Draft-time consequences must be knowable BEFORE the RFx goes out. The
    # shipped version showed "Shakti saves you INR 445,474 a year" on the
    # payment-terms picker, in a conversation whose whole premise is that
    # Shakti has not replied. It was right, traceable, computed in Python and
    # completely indefensible: it told the buyer what to ask for by reading the
    # answers. Everything this project argues collapses if a number can come
    # from the future, so it is asserted rather than remembered.
    print("\n  Pre-quote consequences — nothing from a reply that has not arrived\n")
    names = [s_.vendor.name.split()[0] for s_ in gt.submissions]
    ids = [s_.vendor.vendor_id for s_ in gt.submissions]
    leaks = []
    for row in terms_preview_prior(gt) + gate_preview_prior(gt):
        text = f"{row.get('consequence', '')} {row.get('basis', '')}"
        for n in names + ids:
            if n.lower() in text.lower():
                leaks.append((n, text))
        if row.get("removes") or row.get("removes_names"):
            leaks.append(("removes", str(row)))
    if leaks:
        print("    FAIL — a vendor's unsent answer reached the drafting screen:")
        for n, t in leaks[:5]:
            print(f"      {n}: {t[:90]}")
        return 1
    print(f"    ok    {len(terms_preview_prior(gt))} terms options and "
          f"{len(gate_preview_prior(gt))} gate options name no vendor")
    print( "    ok    they cite last year's contract and the cost of capital,")
    print( "          which is what a buyer has on the day they write an RFx")

    # And the POST-quote versions must still name names — that is their job,
    # and a fix that silenced both would have solved this by deleting the
    # feature rather than by placing it correctly.
    post = gate_preview(gt)
    if not any(r["removes"] for r in post):
        print("    FAIL — the post-quote gate preview names nobody either;")
        print("           the fix removed the measurement instead of moving it")
        return 1
    print( "    ok    after the replies land, the same preview names who a gate removes")
    return 0


# ---------------------------------------------------------------------------
# Consequences the buyer could know BEFORE anyone has replied
# ---------------------------------------------------------------------------
# The draft-time pickers were showing lines like "Shakti saves you INR 445,474 a
# year against 45 days" -- computed, correctly, from Shakti's quote. Which has
# not arrived. The RFx has not gone out.
#
# That is the worst failure available to this project. Everything here argues
# that a buyer should be able to check where a number came from, and a number
# that came from the future cannot be checked at all: it tells them what to ask
# for by reading the answers. A demo that leaks the result into the question is
# doing exactly what it accuses the spreadsheet of.
#
# So before quotes exist, consequences come only from what a buyer actually
# has on the day they write an RFx: last year's awarded rates, the item master,
# and their own cost of capital. Every line says which of those it used.

def terms_preview_prior(gt: GroundTruth, candidates=(30, 45, 60, 90)) -> list[dict]:
    """What moving payment terms costs the BUYER, on last year's awarded spend.

    Not what it does to any vendor's ranking -- nobody has quoted. This is the
    buyer's own working capital: paying sooner costs them the float, paying
    later earns it, at the cost of capital their finance team set. It is the
    one number that is genuinely knowable in advance, it is checkable against
    the FY26 contract, and it is the reason the field matters at all.
    """
    from config import COST_OF_CAPITAL_PCT

    qty = {l.line_no: l.annual_qty for l in gt.rfx.lines}
    base_spend = sum(p.rate_inr * qty.get(p.line_no, 0) for p in gt.prior_contract)
    baseline = 45 if 45 in candidates else candidates[0]
    r = COST_OF_CAPITAL_PCT / 100.0
    covered = len([p for p in gt.prior_contract if p.line_no in qty])

    out = []
    for days in candidates:
        delta_days = days - baseline
        # Same convention as normalize step 8, so the number the buyer reads
        # here and the adjustment applied to quotes later are the same idea.
        worth = base_spend - base_spend / (1 + r * (delta_days / 365.0))
        if days == baseline:
            why = (f"your current terms \u2014 the FY26 contract was written on "
                   f"{baseline} days")
        elif worth > 0:
            why = (f"about INR {abs(worth):,.0f} a year of working capital "
                   f"released, on last year's awarded spend")
        else:
            why = (f"about INR {abs(worth):,.0f} a year of working capital "
                   f"given up, on last year's awarded spend")
        out.append({
            "days": days, "consequence": why,
            "basis": f"FY26 awarded rates on {covered} of {len(gt.rfx.lines)} lines, "
                     f"at {COST_OF_CAPITAL_PCT:.0f}% cost of capital",
            "known_before_quotes": True})
    return out


def gate_preview_prior(gt: GroundTruth) -> list[dict]:
    """Each question, and what GATING it means -- not who it would remove.

    Who it removes is in the answers, and the answers are not in yet. Saying
    "removes Nova" before Nova has replied is a number from the future wearing
    a measurement's clothes. What a buyer can be told in advance is the shape
    of the rule: a gate is a veto, not a score, and a question whose answer is
    a number is a threshold they still have to set.
    """
    out = []
    for q in gt.rfx.questionnaire:
        if q.answer_type == "yes_no":
            why = "a No disqualifies outright \u2014 no trade-off against price"
        elif q.answer_type == "number":
            why = ("gating a number means setting a threshold, and a vendor "
                   "one unit the wrong side of it is out")
        elif q.answer_type == "date":
            why = "an expired or missing date disqualifies, whatever the price"
        else:
            why = "a free-text answer has to be read before it can disqualify"
        out.append({"q_no": q.q_no, "question": q.question,
                    "gating_now": q.gating, "removes": [], "removes_names": [],
                    "consequence": why, "known_before_quotes": True})
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    raise SystemExit(_self_test() if p.parse_args().self_test else 0)
