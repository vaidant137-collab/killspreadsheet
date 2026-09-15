"""
Landed cost. Deterministic, no model, every step nameable.

The comparison table is a lie unless the basis is declared, so this module's
whole job is to turn "what the vendor said" into "cost per buyer unit, on a
stated basis" — and to refuse when it cannot.

Order of operations, and each one can produce a caveat or a refusal:

    1. basis      vendor's unit  -> buyer's unit    (may need a bridge fact)
    2. prior      "same as last year" -> a rate from the FY26 contract
    3. currency   USD -> INR at a dated rate
    4. tax        strip to pre-tax so inclusive and exclusive quotes compare
    5. discount   early-payment terms, if the buyer intends to take them
    6. tooling    dies amortised over the line's annual volume
    7. freight    ex-works loaded to delivered, allocated per unit
    8. npv        differing payment terms discounted to today

Run:  python -m normalize.engine --self-test
"""

from __future__ import annotations

import argparse
import json

from config import COST_OF_CAPITAL_PCT, DATA, GST_PCT
from contracts.normalized import Assumption, CellState, NormalisedLine
from contracts.quote import (
    GroundTruth, Incoterm, QuoteBasis, TaxBasis, VendorLineQuote, VendorProfile,
)
from contracts.rfx import RfxLine, Uom

# ---------------------------------------------------------------------------
# Assumptions. Every one of these is a row in the panel the buyer can edit, and
# every derived number names the ones it used.
# ---------------------------------------------------------------------------

def default_assumptions(gt: GroundTruth) -> dict[str, Assumption]:
    a: dict[str, Assumption] = {
        "cost_of_capital": Assumption(
            key="cost_of_capital", label="Buyer cost of capital",
            value=COST_OF_CAPITAL_PCT, unit="% p.a.",
            source="Buyer finance policy"),
        "take_early_payment": Assumption(
            key="take_early_payment", label="Take early-payment discounts where offered",
            value="yes", source="Buyer working-capital policy"),
        "shipments_per_year": Assumption(
            key="shipments_per_year", label="Inbound shipments per vendor per year",
            value=12, unit="shipments", source="Monthly indent, current practice"),
    }
    for s in gt.submissions:
        if s.vendor.fx_rate_at_quote:
            a[f"fx_{s.vendor.vendor_id}"] = Assumption(
                key=f"fx_{s.vendor.vendor_id}",
                label=f"USD/INR applied to {s.vendor.name}",
                value=s.vendor.fx_rate_at_quote, unit="INR per USD",
                source="Rate stated in the vendor's own offer, at quote date")
    return a


# ---------------------------------------------------------------------------

_UNRESOLVED = object()


def _to_buyer_unit(q: VendorLineQuote, line: RfxLine, rate: float
                   ) -> tuple[float | None, list[str], str | None, str | None]:
    """Convert the vendor's quoting basis to the buyer's unit of measure.

    Returns (value, assumptions_used, unresolved_reason, missing_fact).
    """
    used: list[str] = []
    b, u = q.basis, line.uom

    if b == QuoteBasis.PER_PIECE and u == Uom.PIECE:
        return rate, used, None, None
    if b == QuoteBasis.PER_SET and u == Uom.SET:
        return rate, used, None, None
    if b == QuoteBasis.PER_KG and u == Uom.KG:
        return rate, used, None, None

    if b == QuoteBasis.PER_100:
        if u in (Uom.PIECE, Uom.SET):
            return rate / 100.0, ["per_100_to_unit"], None, None
        if u == Uom.HUNDRED:
            return rate, used, None, None
    if b == QuoteBasis.PER_PIECE and u == Uom.HUNDRED:
        return rate * 100.0, ["unit_to_per_100"], None, None
    if b == QuoteBasis.PER_SET and u == Uom.HUNDRED:
        return rate * 100.0, ["unit_to_per_100"], None, None

    if b == QuoteBasis.PER_KG and u in (Uom.PIECE, Uom.SET, Uom.HUNDRED):
        # The bridge fact. The buyer has dispatch weights for lines they have
        # bought before and none for the ones introduced this year. That is not
        # a gap in the dataset, it is the honest state of a procurement file —
        # and it is the one place the system must refuse rather than estimate.
        if line.unit_weight_g is None:
            return (None, used,
                    f"{q.rate} per kg cannot be converted to a price per "
                    f"{u.value} without the weight of one unit, and no weight "
                    f"is on file for this line.",
                    f"unit_weight_g for line {line.line_no} ({line.code})")
        per_unit = rate * (line.unit_weight_g / 1000.0)
        if u == Uom.HUNDRED:
            per_unit *= 100.0
        return per_unit, ["unit_weight"], None, None

    if b == QuoteBasis.PER_PIECE and u == Uom.SET:
        return rate, ["piece_equals_set"], None, None
    if b == QuoteBasis.PER_SET and u == Uom.PIECE:
        return rate, ["set_equals_piece"], None, None

    return (None, used, f"No conversion defined from {b.value} to {u.value}.",
            f"conversion rule {b.value} -> {u.value}")


def _vendor_annual_units(sub, lines: dict[int, RfxLine]) -> float:
    """Total annual quantity this vendor quoted for, used to spread freight.

    The honest caveat: this assumes the vendor wins everything they quoted. A
    split changes it, and the allocator re-derives freight per subset.
    """
    return sum(lines[q.line_no].annual_qty for q in sub.line_quotes) or 1.0


def normalise_line(q: VendorLineQuote, line: RfxLine, v: VendorProfile,
                   gt: GroundTruth, vendor_annual_units: float) -> NormalisedLine:
    used: list[str] = []
    caveats: list[str] = []
    as_quoted = _describe(q, line, v)

    n = NormalisedLine(vendor_id=v.vendor_id, line_no=line.line_no,
                       buyer_uom=line.uom, as_quoted=as_quoted,
                       landed_inr=None, state=CellState.UNRESOLVED)

    # --- 2. "rest same as last year" is a pointer, not a price --------------
    rate = q.rate
    if q.refers_to_prior_contract:
        prior = next((p for p in gt.prior_contract if p.line_no == line.line_no), None)
        if prior is None:
            n.unresolved_reason = (
                'The vendor wrote "rest same as last year", but this line was '
                "introduced this year and does not appear in the FY26 rate contract.")
            n.missing_fact = f"a prior rate for line {line.line_no}"
            return n
        rate = prior.rate_inr
        used.append("prior_contract")
        caveats.append("Rate taken from the FY26 rate contract, not from this quote.")

    if rate is None:
        n.unresolved_reason = "No rate was quoted for this line."
        n.missing_fact = f"a rate for line {line.line_no}"
        return n

    # --- 1. basis -----------------------------------------------------------
    value, u_used, reason, missing = _to_buyer_unit(q, line, rate)
    if value is None:
        n.unresolved_reason, n.missing_fact = reason, missing
        n.assumptions_used = used
        return n
    used += u_used
    base_native = value

    # --- 3. currency --------------------------------------------------------
    if q.currency != "INR":
        fx = v.fx_rate_at_quote
        if not fx:
            n.unresolved_reason = f"Quoted in {q.currency} with no exchange rate stated."
            n.missing_fact = f"an {q.currency}/INR rate"
            return n
        value *= fx
        used.append(f"fx_{v.vendor_id}")
        caveats.append(f"Converted from {q.currency} at {fx:.2f}; the buyer carries "
                       f"the movement between award and delivery.")

    # --- 4. tax -------------------------------------------------------------
    if v.tax_basis == TaxBasis.GST_INCLUDED:
        value /= (1 + GST_PCT / 100.0)
        used.append("gst_strip")
        caveats.append(f"Quoted inclusive of GST; stripped to pre-tax at "
                       f"{GST_PCT:.0f}% so it compares with exclusive quotes.")

    # --- 5. early-payment discount ------------------------------------------
    discount = 0.0
    if v.early_payment_discount_pct:
        discount = value * v.early_payment_discount_pct / 100.0
        value -= discount
        used.append("take_early_payment")
        caveats.append(
            f"{v.early_payment_discount_pct:.0f}% early-payment discount applied "
            f"(payment within {v.early_payment_within_days} days). Stated only in a "
            f"footnote, not in the rate schedule.")

    # --- 6. tooling ---------------------------------------------------------
    tooling = 0.0
    if q.tooling_inr:
        tooling = q.tooling_inr / max(line.annual_qty, 1)
        value += tooling
        used.append("tooling_amortisation")
        caveats.append(
            f"Die charged separately at INR {q.tooling_inr:,.0f}; amortised over "
            f"{line.annual_qty:,} units. Awarding fewer units raises this.")
    if q.tooling_amortised:
        caveats.append(
            "Die cost is already inside the unit rate. It is therefore invisible "
            "at this volume and voids the quoted price at a lower one.")

    # --- 7. freight ---------------------------------------------------------
    freight = 0.0
    if v.incoterm in (Incoterm.EX_WORKS, Incoterm.FREIGHT_EXTRA) and v.freight_inr_per_shipment:
        annual_freight = v.freight_inr_per_shipment * v.shipments_per_year
        freight = annual_freight / vendor_annual_units
        value += freight
        used += ["shipments_per_year"]
        caveats.append(
            f"Quoted {v.incoterm.value.replace('_', ' ')}; freight loaded at "
            f"INR {freight:.2f} per unit, assuming they win every line they quoted. "
            f"A split raises this.")

    # --- 8. payment terms ---------------------------------------------------
    npv_adj = 0.0
    required_days = _required_payment_days(gt)
    if v.payment_days and v.payment_days != required_days:
        # Only the DIFFERENCE from the buyer's stated terms is an adjustment.
        # A vendor who quoted on exactly the requested basis needed no
        # assumption, and must not be marked derived for our benefit.
        delta_days = v.payment_days - required_days
        factor = 1 + (COST_OF_CAPITAL_PCT / 100.0) * (delta_days / 365.0)
        npv = value / factor
        npv_adj = npv - value
        value = npv
        used.append("cost_of_capital")
        caveats.append(
            f"{v.payment_days}-day payment terms against the {required_days} days "
            f"asked for, discounted at {COST_OF_CAPITAL_PCT:.0f}%. Worth "
            f"INR {abs(npv_adj):.2f} per unit "
            f"{'in their favour' if npv_adj < 0 else 'against them'}.")

    if q.excludes_sub_component and line.sub_components:
        caveats.append(
            f"Excludes {line.sub_components[0].lower()}, which this line includes. "
            f"Not a cheaper quote — a different one.")

    n.landed_inr = round(value, 4)
    n.base_inr = round(base_native, 4)
    n.freight_inr = round(freight, 4) or None
    n.tooling_inr = round(tooling, 4) or None
    n.discount_inr = round(-discount, 4) or None
    n.npv_adjustment_inr = round(npv_adj, 4) or None
    n.assumptions_used = used
    n.caveats = caveats
    n.state = CellState.EXTRACTED if not used else CellState.DERIVED
    return n


def _required_payment_days(gt: GroundTruth) -> int:
    import re
    m = re.search(r"(\d+)", gt.rfx.required_payment_terms)
    return int(m.group(1)) if m else 45


def _describe(q: VendorLineQuote, line: RfxLine, v: VendorProfile) -> str:
    if q.refers_to_prior_contract:
        return '"rest same as last year"'
    if q.rate is None:
        return "no quote"
    sym = "$" if q.currency == "USD" else "Rs "
    w = v.unit_wording.replace("Per ", "").strip()
    unit = {QuoteBasis.PER_PIECE: w, QuoteBasis.PER_KG: "kg",
            QuoteBasis.PER_100: w if "100" in w else f"100 {w}",
            QuoteBasis.PER_SET: "set"}[q.basis]
    return f"{sym}{q.rate:,.4g} / {unit}"


def normalise_all(gt: GroundTruth) -> list[NormalisedLine]:
    lines = {l.line_no: l for l in gt.rfx.lines}
    out: list[NormalisedLine] = []
    for sub in gt.submissions:
        annual_units = _vendor_annual_units(sub, lines)
        for q in sub.line_quotes:
            out.append(normalise_line(q, lines[q.line_no], sub.vendor, gt, annual_units))
    return out


# ---------------------------------------------------------------------------

def _self_test() -> int:
    gt = GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    rows = normalise_all(gt)

    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r.state.value] = by_state.get(r.state.value, 0) + 1

    print(f"\n  {len(rows)} vendor-line cells normalised")
    for k, v in sorted(by_state.items()):
        print(f"    {k:12s} {v:3d}")

    clean = [r for r in rows if r.state == CellState.EXTRACTED]
    print(f"\n  Cells comparable exactly as quoted, with no assumption at all: "
          f"{len(clean)} of {len(rows)}")
    if not clean:
        print("  Not one. Every vendor departed from the buyer's stated basis on")
        print("  every line — unit, currency, tax, Incoterm or payment terms.")

    freq: dict[str, int] = {}
    for r in rows:
        for a in set(r.assumptions_used):
            freq[a] = freq.get(a, 0) + 1
    print("\n  What had to be assumed, and how often:")
    for k, v in sorted(freq.items(), key=lambda kv: -kv[1]):
        print(f"    {k:24s} {v:3d} cells")

    print("\n  Line 6 — one buyer line, five bases, all landed to Rs/piece:\n")
    print(f"    {'vendor':10s} {'as quoted':24s} {'landed':>9s}  state")
    for r in [x for x in rows if x.line_no == 6]:
        val = f"{r.landed_inr:9.2f}" if r.landed_inr is not None else "        —"
        print(f"    {r.vendor_id:10s} {r.as_quoted:24s} {val}  {r.state.value}")
        for c in r.caveats:
            print(f"      · {c}")

    unres = [r for r in rows if r.state == CellState.UNRESOLVED]
    print(f"\n  {len(unres)} cells the system refuses to guess:\n")
    for r in unres[:8]:
        print(f"    {r.vendor_id:10s} line {r.line_no:2d}  needs: {r.missing_fact}")
    if len(unres) > 8:
        print(f"    ... and {len(unres) - 8} more")

    # The whole point: no unresolved cell ever carries a number.
    bad = [r for r in unres if r.landed_inr is not None]
    assert not bad, f"{len(bad)} unresolved cells carry a value — the refusal rule is broken"
    print("\n  ✓ no unresolved cell carries a number\n")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    raise SystemExit(_self_test() if a.self_test else 0)
