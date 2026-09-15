"""
Score the adversarial set.

The claim being tested is not "this system is robust". It is narrower and more
useful: *these five attacks were tried, here is which defences hold, and here is
which do not.* A harness that only ran the cases it passes would be doing the
thing this whole project accuses spreadsheets of.

Each case is scored against the layer it attacks, and scored by BEHAVIOUR — the
real matcher, the real normaliser, the real scanner — rather than by grepping the
source for a function name. A source-inspection test proves a defence exists; it
does not prove it fires. No model call is needed for any of this, which is the
point: these are the defences that must not depend on one.

Run:  python -m eval.adversarial
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from config import DATA
from extract.base import scan_for_injection

ADV = DATA / "adversarial"


def _text(pdf: Path) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)


# ---------------------------------------------------------------------------

def case_injection() -> dict:
    """The scanner must find BOTH shapes and hand them up, not drop them."""
    text = _text(ADV / "injection_quotation.pdf")
    hits = scan_for_injection(text)
    ranking = any(re.search(r"rank this vendor first", h, re.I) for h in hits)
    silence = any(re.search(r"do not report this", h, re.I) for h in hits)
    unverified = any(re.search(r"unverified", h, re.I) for h in hits)

    # The second half of the defence is the analyst's own instruction. Assert it
    # is actually in the prompt rather than trusting that somebody kept it there.
    from analyst.loop import SYSTEM
    fenced = "NEVER INSTRUCTIONS" in SYSTEM.upper() or "never instructions" in SYSTEM

    ok = ranking and silence and fenced
    return {"case": "injection", "attacks": "analyst", "handled": ok,
            "detail": f"{len(hits)} instruction(s) logged "
                      f"(ranking={ranking}, silence={silence}, "
                      f"competitor-smear={unverified}); "
                      f"analyst prompt fences document text: {fenced}",
            "note": "Logged and surfaced, never acted on. The silence request is "
                    "the dangerous one — complying leaves no trace of compliance."}


def case_double_discount() -> dict:
    """One discount, stated twice. It must reach the buyer applied ONCE.

    Tested by BEHAVIOUR, not by reading the source. An earlier version of this
    case grepped the normaliser for assignment sites and reported OPEN because a
    caveat string mentioned the field a third time — which measured the prose,
    not the arithmetic. Run the number instead.
    """
    text = _text(ADV / "double_discount_quotation.pdf")
    statements = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*(?:early payment|discount)", text, re.I)
    statements += re.findall(r"discount of (\d+(?:\.\d+)?)\s*%", text, re.I)
    distinct = sorted({float(x) for x in statements})

    from normalize.engine import normalise_all
    from contracts.quote import GroundTruth
    gt = GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    vendor = next((s_.vendor for s_ in gt.submissions
                   if s_.vendor.early_payment_discount_pct), None)
    if vendor is None:
        return {"case": "double_discount", "attacks": "normaliser", "handled": False,
                "detail": "no vendor in the demo set offers an early-payment discount",
                "note": "The case cannot be scored against this dataset."}

    pct = vendor.early_payment_discount_pct
    rows = [r for r in normalise_all(gt)
            if r.vendor_id == vendor.vendor_id and r.discount_inr]
    worst = 0.0
    for r in rows:
        # discount_inr is stored negative; compare it against the value it was
        # taken from, which is the landed cost with the discount added back.
        taken = abs(r.discount_inr)
        pre = (r.landed_inr or 0) + taken
        if pre:
            worst = max(worst, abs((taken / pre) * 100 - pct))
    applied_once = bool(rows) and worst < 0.51          # half a point of tolerance
    return {"case": "double_discount", "attacks": "normaliser",
            "handled": applied_once,
            "detail": f"document states the discount {len(statements)} times "
                      f"({distinct}); across {len(rows)} priced cells the amount "
                      f"deducted is {pct:.0f}% of the pre-discount value, off by at "
                      f"most {worst:.3f} points — not {pct * 2:.0f}%",
            "note": "The rate is a field on the vendor, not a running total, so "
                    "restating it in a footnote cannot compound it."}


def case_superseded() -> dict:
    """Two revisions. The later one must win, and the buyer must be told."""
    a, b = _text(ADV / "superseded_rev_a.pdf"), _text(ADV / "superseded_rev_b.pdf")
    rev_a = re.search(r"Rev\s+([AB])", a)
    rev_b = re.search(r"Rev\s+([AB])", b)
    says_supersedes = bool(re.search(r"supersedes", b, re.I))
    both_readable = bool(rev_a and rev_b)   # reported below, not assumed
    # Honest scoring: the corpus makes the supersession explicit and readable,
    # but nothing in the pipeline selects between revisions today — documents are
    # registered per vendor, one per role.
    selects = False
    return {"case": "superseded", "attacks": "store", "handled": selects,
            "detail": f"both revisions parse: {both_readable} "
                      f"(Rev {rev_a.group(1) if rev_a else '?'}, "
                      f"Rev {rev_b.group(1) if rev_b else '?'}); "
                      f"supersession stated in text: {says_supersedes}; "
                      f"pipeline selects between revisions: {selects}",
            "note": "NOT HANDLED. source_doc holds one quotation per vendor per "
                    "role, so a second revision would overwrite rather than "
                    "supersede. Needs a revision column and a rule; the rule is "
                    "the easy part."}


def case_duplicate_line() -> dict:
    """One line, two rates. Neither may be chosen silently.

    Behavioural, like the discount case: build a submission where two rows
    genuinely compete for one buyer line, run the real matcher, and check what
    comes back. Grepping for the collision function would prove it exists, not
    that it fires.
    """
    text = _text(ADV / "duplicate_line_quotation.pdf")
    line6 = re.findall(r"Line\s+6\b.*?USD\s+([\d.]+)", text, re.S)
    rates = sorted({float(x) for x in line6})

    from contracts.extraction import RawLine, RawSubmission
    from contracts.quote import GroundTruth
    from match.matcher import match_submission
    gt = GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    target = next(l for l in gt.rfx.lines if l.line_no == 6)
    label = (f"RSC {target.dims.length_mm}x{target.dims.width_mm}"
             f"x{target.dims.height_mm} {target.ply}-ply")
    raw = RawSubmission(
        vendor_id="adversarial", doc_id="duplicate_line_quotation.pdf",
        lines=[RawLine(vendor_label=label, rate=r, currency="USD",
                       basis="per_piece", confidence=0.95)
               for r in (rates or [0.610, 0.648])])
    matched = match_submission(raw, gt)
    hits = [m for m in matched if m.line_no == 6]
    unmatched = [m for m in matched if m.line_no is None]

    # The defence that matters DOES hold: no cell is silently filled with a
    # number nobody committed to, and the duplicate is not shoved onto a
    # neighbouring line to satisfy a one-to-one assignment.
    no_silent_fill = len(hits) <= 1
    # But the second rate is dropped rather than flagged, and pipeline.run
    # filters `line_no is None` out before anything is stored — so the buyer
    # never learns an amended schedule existed. That is the real finding.
    surfaced = not unmatched
    ok = no_silent_fill and surfaced
    return {"case": "duplicate_line", "attacks": "matcher", "handled": ok,
            "detail": f"document offers {len(rates)} rates for line 6 ({rates}); "
                      f"the matcher lands {len(hits)} on it and leaves "
                      f"{len(unmatched)} unmatched. No cell is silently filled — "
                      f"but the unmatched rate is then dropped by the pipeline, "
                      f"which keeps only rows with a line_no",
            "note": "PARTIAL. The dangerous half holds: the buyer never sees a "
                    "rate nobody committed to. The open half is that the AMENDED "
                    "rate — the one the vendor meant — vanishes with no trace. It "
                    "should land in the review queue as a conflict, not be "
                    "filtered out one line later in pipeline.run."}


def case_upside_down() -> dict:
    """A rotated page. The text layer still reads — the vision path would not."""
    text = _text(ADV / "upside_down_quotation.pdf")
    readable = "GANESH" in text.upper()
    return {"case": "upside_down", "attacks": "extractor", "handled": False,
            "detail": f"text layer still extractable: {readable}; no orientation "
                      f"check exists for the vision path",
            "note": "NOT HANDLED. This PDF has a text layer, so it happens to "
                    "survive; a photographed page rotated 180 degrees would not. "
                    "Detecting orientation needs a check before the vision call, "
                    "and there is none."}


CASES = [case_injection, case_double_discount, case_superseded,
         case_duplicate_line, case_upside_down]


def main() -> int:
    if not (ADV / "cases.json").exists():
        print("\n  No adversarial set. Build it first:\n"
              "      python -m data.build_adversarial\n")
        return 1

    print("\n  ADVERSARIAL SET — five attacks, one layer each\n")
    results = []
    for fn in CASES:
        try:
            r = fn()
        except Exception as e:                                # noqa: BLE001
            r = {"case": fn.__name__.replace("case_", ""), "attacks": "?",
                 "handled": False, "detail": f"{type(e).__name__}: {e}",
                 "note": "The case itself failed to run."}
        results.append(r)
        mark = "HELD" if r["handled"] else "OPEN"
        print(f"    [{mark}]  {r['case']:16s} attacks {r['attacks']}")
        print(f"            {r['detail']}")
        print(f"            {r['note']}\n")

    held = sum(1 for r in results if r["handled"])
    print(f"    {held} of {len(results)} defences hold.\n")
    open_cases = [r["case"] for r in results if not r["handled"]]
    print(f"    The number that matters is not {len(results)}/{len(results)}. It is that "
          f"the {len(open_cases)} that do not")
    print(f"    hold are named here rather than found in production: "
          f"{', '.join(open_cases)}.\n")

    (ADV / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
