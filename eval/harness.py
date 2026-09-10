"""
Does this actually work, and how would we know?

Four metrics, not one, because they fail differently:

  field accuracy   is the number right?
  unit accuracy    is the UNIT right?  Scored separately, because a right number
                   in the wrong unit is worse than a missing number - it is
                   plausible, comparable, and wrong by a factor of forty.
  match accuracy   did it land on the correct buyer line?  A 3-ply price on a
                   5-ply line is a perfect extraction with a catastrophic result.
  escape rate      of the errors that occurred, how many got PAST the confidence
                   gate into a cell the buyer would trust?

Escape rate is the one that matters. A system that is 90% accurate and catches
every one of its own errors is deployable. A system that is 98% accurate and
hides its 2% is not, because the 98% is unverifiable without the refusals.

Plus calibration: bucket every cell by confidence and measure accuracy inside
each bucket. If the 0.9 bucket is 92% accurate the score means something. If
every bucket is 85%, the confidence score is decoration and should be REMOVED
rather than displayed - being willing to say that is itself the point.

Run:  python -m eval.harness
"""

from __future__ import annotations

import json
from collections import defaultdict

from config import DATA, REVIEW_THRESHOLD
from contracts.extraction import SourceDoc
from contracts.quote import GroundTruth
from extract.base import get_extractor
from match.matcher import match_submission

RATE_TOL = 0.005          # half a percent; below that is float noise, not error


class Scorecard:
    def __init__(self) -> None:
        self.n = 0
        self.field_ok = self.unit_ok = self.match_ok = 0
        self.errors: list[dict] = []
        self.buckets: dict[str, list[bool]] = defaultdict(list)

    def add(self, *, gold, got, conf: float) -> None:
        self.n += 1
        f = _rate_eq(gold["rate"], got.rate)
        u = gold["basis"] == got.basis
        m = gold["line_no"] == got.line_no
        self.field_ok += f; self.unit_ok += u; self.match_ok += m
        ok = f and u and m
        self.buckets[_bucket(conf)].append(ok)
        if not ok:
            self.errors.append({
                "vendor": got.vendor_id, "expected_line": gold["line_no"],
                "got_line": got.line_no, "label": got.vendor_label,
                "field": f, "unit": u, "match": m, "confidence": round(conf, 3),
                "escaped": conf >= REVIEW_THRESHOLD,
                "expected_rate": gold["rate"], "got_rate": got.rate,
            })

    def add_miss(self, *, gold, vendor_id: str, unmatched) -> None:
        """A gold line nothing was matched to. Counts against every metric --
        a line the system silently dropped is not a line it got right."""
        self.n += 1
        self.buckets["below 0.70"].append(False)
        self.errors.append({
            "vendor": vendor_id, "expected_line": gold["line_no"], "got_line": None,
            "label": ("no row matched this line" if not unmatched else
                      f"no row matched this line; {len(unmatched)} rows matched nothing"),
            "field": False, "unit": False, "match": False, "confidence": 0.0,
            "escaped": False, "expected_rate": gold["rate"], "got_rate": None,
        })

    def report(self) -> None:
        pct = lambda a: f"{a / self.n:6.1%}" if self.n else "   n/a"
        escapes = [e for e in self.errors if e["escaped"]]
        caught = [e for e in self.errors if not e["escaped"]]

        print(f"\n  EXTRACTION SCORECARD          {self.n} vendor-line cells\n")
        print(f"    field accuracy   {pct(self.field_ok)}   is the number right")
        print(f"    unit accuracy    {pct(self.unit_ok)}   is the unit right")
        print(f"    match accuracy   {pct(self.match_ok)}   did it hit the right buyer line")
        print(f"    ---")
        print(f"    errors           {len(self.errors):6d}")
        print(f"    caught by gate   {len(caught):6d}   routed to human review")
        print(f"    ESCAPED          {len(escapes):6d}   reached a cell the buyer would trust")
        if self.errors:
            rate = len(escapes) / len(self.errors)
            print(f"    escape rate      {rate:6.1%}   <- the metric that matters")

        print(f"\n  CALIBRATION                   threshold {REVIEW_THRESHOLD}\n")
        print(f"    {'confidence':12s} {'cells':>6s} {'accurate':>9s}")
        for b in sorted(self.buckets, reverse=True):
            v = self.buckets[b]
            print(f"    {b:12s} {len(v):6d} {sum(v) / len(v):9.1%}")
        _calibration_verdict(self.buckets)

        if escapes:
            print(f"\n  ESCAPES — errors the gate did not catch:\n")
            for e in escapes:
                print(f"    {e['vendor']:9s} {e['label'][:34]:34s} "
                      f"expected line {e['expected_line']}, got {e['got_line']}  "
                      f"conf {e['confidence']}")
        if caught:
            print(f"\n  Caught by the gate ({len(caught)}) — these are the queue:\n")
            for e in caught[:6]:
                print(f"    {e['vendor']:9s} {e['label'][:34]:34s} conf {e['confidence']}")
            if len(caught) > 6:
                print(f"    ... and {len(caught) - 6} more")


def _rate_eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(RATE_TOL, abs(a) * RATE_TOL)


def _bucket(c: float) -> str:
    for lo in (0.95, 0.90, 0.80, 0.70, 0.0):
        if c >= lo:
            return f"{lo:.2f}-{min(lo + 0.05, 1.0):.2f}" if lo >= 0.9 else \
                   f"{lo:.2f}+" if lo else "below 0.70"
    return "below 0.70"


def _calibration_verdict(buckets: dict[str, list[bool]]) -> None:
    acc = {b: sum(v) / len(v) for b, v in buckets.items() if len(v) >= 3}
    if len(acc) < 2:
        print("\n    Too few populated buckets to judge calibration.")
        return
    spread = max(acc.values()) - min(acc.values())
    if spread < 0.10:
        print(f"\n    Accuracy varies by only {spread:.1%} across confidence buckets.")
        print("    The score is not discriminating. It should be REMOVED from the UI")
        print("    rather than displayed — a number that buys trust it has not earned")
        print("    is worse than no number.")
    else:
        print(f"\n    Accuracy spans {spread:.1%} across buckets — the score discriminates,")
        print("    so the threshold can be set on evidence rather than on feel.")


def run() -> Scorecard:
    gt = GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    ex = get_extractor("fixture")
    card = Scorecard()

    for sub in gt.submissions:
        vid = sub.vendor.vendor_id
        raw = ex.extract(SourceDoc(doc_id=f"{vid}-quote", vendor_id=vid, path="",
                                   kind=sub.vendor.reply_format, role="quote"))
        matched = match_submission(raw, gt)
        # Iterate the GOLD set, not the output. Scoring what we emitted lets an
        # unmatched line score as "correctly matched to nothing", which is how a
        # harness ends up flattering the system it is supposed to audit.
        by_line = {m.line_no: m for m in matched if m.line_no is not None}
        unmatched = [m for m in matched if m.line_no is None]
        for q in sub.line_quotes:
            g = {"line_no": q.line_no, "rate": q.rate, "basis": q.basis.value}
            m = by_line.get(q.line_no)
            if m is None:
                card.add_miss(gold=g, vendor_id=vid, unmatched=unmatched)
                continue
            card.add(gold=g, got=m,
                     conf=min(m.extraction_confidence, m.match_confidence))
    return card


if __name__ == "__main__":
    run().report()
    print()
