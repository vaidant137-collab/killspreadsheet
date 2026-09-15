"""
Vendor line -> buyer line. The part that breaks quietly in production.

Getting Rs 42/kg out of a document is easy. Knowing which of the buyer's thirty
lines it belongs to is not, and the failure mode is silent: a 3-ply price landed
on a 5-ply line is a perfect extraction with a plausible number in a plausible
cell, and nobody finds out until goods receipt.

So match confidence is scored SEPARATELY from extraction confidence, and it is
derived from the margin between the best candidate and the runner-up. A label
that fits two lines almost equally well is not a 0.9 match to the better one; it
is an ambiguous match that a human should look at.

Deliberately deterministic. Every score is explainable in one sentence, which
matters more here than a couple of points of accuracy — and it means this seam
can be swapped for a model or a trained classifier later without the rest of the
system noticing, exactly as `contracts/extraction.LineMatch` intends.

Run:  python -m match.matcher --self-test
"""

from __future__ import annotations

import argparse
import json
import re

from config import DATA
from contracts.extraction import ExtractedQuoteLine, RawLine, RawSubmission
from contracts.quote import GroundTruth
from contracts.rfx import BoxStyle, Rfx, RfxLine

MM_PER_INCH = 25.4
# A supplier rounds 450 mm to 18 inches before we ever see it, so up to half an
# inch of loss per axis is baked in. Tolerate it; do not pretend it isn't there.
INCH_TOL_MM = 15.0
MM_TOL_MM = 6.0

# Ply is written at least four ways in this dataset alone: "5 Ply" (Shakti),
# "5P" (Nova), "FIVE-PLY" (Meridian), "5PLY" (Ganesh). None of them is wrong.
_PLY_PATTERNS = [re.compile(p, re.I) for p in (
    r"(\d+)\s*-?\s*ply", r"\b(\d)\s*P\b")]
_PLY_WORDS = {"two": 2, "three": 3, "five": 5, "seven": 7}
# Dimensions may be single-digit when quoted in inches: "12X8X6" is a real label.
_DIMS = re.compile(r"(\d{1,4})\s*[xX×]\s*(\d{1,4})(?:\s*[xX×]\s*(\d{1,4}))?")

_STYLE_HINTS = {
    BoxStyle.DIECUT_0427: ("diecut", "die-cut", "die cut", "mailer"),
    BoxStyle.SHEET: ("sheet",),
    BoxStyle.PAD: ("pad",),
    BoxStyle.PARTITION: ("partn", "partition", "fitment", "cap+tray", "captray"),
    BoxStyle.HSC_0203: ("export carton", "export", "hsc"),
    BoxStyle.RSC_0201: ("rsc", "case", "box"),
}


def _ply_of(label: str) -> int | None:
    for pat in _PLY_PATTERNS:
        m = pat.search(label)
        if m:
            return int(m.group(1))
    t = label.lower()
    for w, n in _PLY_WORDS.items():
        if f"{w}-ply" in t or f"{w} ply" in t:
            return n
    return None


def _style_of(label: str) -> BoxStyle | None:
    t = label.lower()
    for style in (BoxStyle.DIECUT_0427, BoxStyle.SHEET, BoxStyle.PAD,
                  BoxStyle.PARTITION, BoxStyle.HSC_0203, BoxStyle.RSC_0201):
        if any(h in t for h in _STYLE_HINTS[style]):
            return style
    return None


def _dims_mm(label: str, system: str) -> tuple[int, ...] | None:
    m = _DIMS.search(label)
    if not m:
        return None
    vals = [int(x) for x in m.groups() if x]
    if system == "inch":
        vals = [round(v * MM_PER_INCH) for v in vals]
    return tuple(vals)


def _cells(label: str) -> str | None:
    t = label.lower()
    if "4c" in t or "4 cell" in t or "4-cell" in t:
        return "4CELL"
    if "6c" in t or "6 cell" in t or "6-cell" in t:
        return "6CELL"
    if "cap" in t and "tray" in t:
        return "CAPTRAY"
    return None


def score(raw: RawLine, line: RfxLine) -> tuple[float, list[str]]:
    """0..1, with the reasons. Anything that cannot be explained is not scored.

    Scored against what the label ACTUALLY CLAIMS, not against a fixed maximum.
    A vendor who omits ply has not given us a weaker match, they have given us
    less to go on — penalising them for information they never asserted would
    make every terse label look ambiguous and bury the genuinely ambiguous ones.
    """
    why: list[str] = []
    earned = possible = 0.0

    ply = _ply_of(raw.vendor_label)
    if ply and line.ply:
        possible += 0.30
        if ply == line.ply:
            earned += 0.30; why.append(f"{line.ply}-ply matches")
        else:
            return 0.0, [f"ply {ply} != {line.ply}"]

    st = _style_of(raw.vendor_label)
    if st:
        # Style is a weak signal and vendors use the words loosely: Meridian
        # calls a die-cut mailer a "CASE". Dimensions and ply are far stronger
        # evidence, so a style disagreement costs points and earns a caveat --
        # it does not veto a match the geometry supports.
        possible += 0.20
        if st == line.style:
            earned += 0.20; why.append(f"style {st.value} matches")
        elif {st, line.style} == {BoxStyle.RSC_0201, BoxStyle.HSC_0203}:
            earned += 0.10; why.append("box-family match, style differs")
        else:
            why.append(f"vendor calls it '{st.value}', the RFx line is "
                       f"'{line.style.value}' — dimensions and ply agree")

    d = _dims_mm(raw.vendor_label, raw.dimension_system)
    if d:
        possible += 0.40
        want = [line.dims.length_mm, line.dims.width_mm]
        if line.dims.height_mm:
            want.append(line.dims.height_mm)
        tol = INCH_TOL_MM if raw.dimension_system == "inch" else MM_TOL_MM
        if len(d) != len(want):
            return 0.0, [f"{len(d)} dimensions given, {len(want)} expected"]
        drift = [abs(a - b) for a, b in zip(d, want)]
        worst = max(drift)
        if worst <= tol:
            # Graded, not pass/fail. Two SKUs 20 mm apart both round to labels
            # that sit inside the tolerance an inch conversion forces on us, so
            # a threshold cannot separate them and a distance can: 6 mm of drift
            # is better evidence than 15 mm, and the assignment step below uses
            # exactly that difference to pair rows with lines correctly.
            earned += 0.40 * (1.0 - 0.55 * worst / tol)
            why.append(
                f"dimensions within {worst:.0f} mm" +
                (f" (converted from inches, {tol:.0f} mm tolerance)"
                 if raw.dimension_system == "inch" else ""))
        else:
            return 0.0, [f"dimensions differ by up to {worst:.0f} mm"]

    c = _cells(raw.vendor_label)
    if c:
        possible += 0.10
        if c in line.code:
            earned += 0.10; why.append(f"{c} suffix matches")
        else:
            return 0.0, [f"{c} does not match {line.code}"]

    # A label that contradicts itself is a real thing in this market
    # ("Double Wall 3 Ply" is single wall by definition). Match it, but say so.
    if "dbl wall" in raw.vendor_label.lower() and line.ply == 3:
        why.append("label says 'DBL WALL' on a 3-ply item, which is self-contradictory")

    if possible == 0:
        return 0.0, ["the label asserts nothing that can be matched on"]
    return min(earned / possible, 1.0), why


def match_line(raw: RawLine, rfx: Rfx) -> tuple[int | None, float, str]:
    scored = []
    for line in rfx.lines:
        sc, why = score(raw, line)
        if sc > 0:
            scored.append((sc, line.line_no, "; ".join(why)))
    if not scored:
        return None, 0.0, "no line in the RFx is consistent with this label"
    scored.sort(reverse=True)
    best_s, best_no, why = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0

    # Confidence is the MARGIN, not the score. A label fitting two lines almost
    # equally well is ambiguous, not a confident match to the marginally better.
    margin = best_s - runner
    conf = min(0.99, best_s * (0.55 + 0.45 * min(margin / 0.30, 1.0)))
    if runner > 0:
        why += f"; next best scored {runner:.2f}"
    return best_no, round(conf, 3), why


def match_submission(raw: RawSubmission, gt: GroundTruth) -> list[ExtractedQuoteLine]:
    rfx = gt.rfx
    out: list[ExtractedQuoteLine] = []
    claimed: set[int] = set()
    ordinary: list[RawLine] = []

    for rl in raw.lines:
        # --- class rates: one stated rate covering many lines ---------------
        pm = re.match(r"(\d+)-ply board", rl.vendor_label, re.I)
        if pm and rl.basis == "per_kg":
            ply = int(pm.group(1))
            covered = [l for l in rfx.lines if l.ply == ply and l.style in (
                BoxStyle.RSC_0201, BoxStyle.DIECUT_0427, BoxStyle.SHEET)]
            for l in covered:
                claimed.add(l.line_no)
                out.append(ExtractedQuoteLine(
                    vendor_id=raw.vendor_id, line_no=l.line_no,
                    vendor_label=rl.vendor_label, rate=rl.rate, currency=rl.currency,
                    basis=rl.basis, tooling_inr=rl.tooling_inr,
                    tooling_amortised=rl.tooling_amortised, note=rl.note,
                    evidence=rl.evidence, extraction_confidence=rl.confidence,
                    match_confidence=0.82,
                    match_rationale=f"Rate stated for {ply}-ply board as a grade; applied "
                                    f"to all {len(covered)} board lines of that ply. The "
                                    f"vendor named no items, so coverage is inferred."))
            continue

        # --- a pointer to a prior document, not a price ---------------------
        if rl.refers_to_prior_contract:
            rest = [l for l in rfx.lines if l.line_no not in claimed]
            for l in rest:
                out.append(ExtractedQuoteLine(
                    vendor_id=raw.vendor_id, line_no=l.line_no,
                    vendor_label=rl.vendor_label, rate=None, currency=rl.currency,
                    basis=rl.basis, refers_to_prior_contract=True, note=rl.note,
                    evidence=rl.evidence, extraction_confidence=rl.confidence,
                    match_confidence=0.75,
                    match_rationale=f'"rest same as last year" applied to the {len(rest)} '
                                    f"lines not covered by a stated ply rate."))
            continue

        ordinary.append(rl)

    out += _assign(ordinary, rfx, raw.vendor_id, claimed)
    _flag_collisions(out)
    return out


def _assign(rows: list[RawLine], rfx: Rfx, vendor_id: str,
            claimed: set[int]) -> list[ExtractedQuoteLine]:
    """Assign rows to lines globally, best evidence first.

    A row picking its own favourite line independently is how two labels end up
    on one line while its neighbour goes unquoted -- and the unquoted one is the
    silent half of that failure. Scoring every pair and then assigning the
    strongest pairs first, one line and one row each, fixes the common case
    where rounding made two labels look interchangeable.
    """
    pairs: list[tuple[float, int, int, str, float]] = []
    for i, rl in enumerate(rows):
        scored = []
        for line in rfx.lines:
            sc, why = score(rl, line)
            if sc > 0:
                scored.append((sc, line.line_no, "; ".join(why)))
        scored.sort(reverse=True)
        for rank, (sc, line_no, why) in enumerate(scored):
            runner = scored[1][0] if len(scored) > 1 else 0.0
            margin = sc - runner if rank == 0 else 0.0
            conf = min(0.99, sc * (0.55 + 0.45 * min(margin / 0.30, 1.0)))
            pairs.append((sc, i, line_no, why, round(conf, 3)))

    pairs.sort(key=lambda p: -p[0])
    used_rows: set[int] = set()
    used_lines: set[int] = set(claimed)
    chosen: dict[int, tuple[int, str, float]] = {}
    for sc, i, line_no, why, conf in pairs:
        if i in used_rows or line_no in used_lines:
            continue
        used_rows.add(i); used_lines.add(line_no)
        chosen[i] = (line_no, why, conf)

    out: list[ExtractedQuoteLine] = []
    for i, rl in enumerate(rows):
        line_no, why, conf = chosen.get(
            i, (None, "no line in the RFx is consistent with this label", 0.0))
        out.append(ExtractedQuoteLine(
            vendor_id=vendor_id, line_no=line_no, vendor_label=rl.vendor_label,
            rate=rl.rate, currency=rl.currency, basis=rl.basis,
            tooling_inr=rl.tooling_inr, tooling_amortised=rl.tooling_amortised,
            note=rl.note, evidence=rl.evidence,
            extraction_confidence=rl.confidence, match_confidence=conf,
            match_rationale=why))
    return out


def _flag_collisions(matched: list[ExtractedQuoteLine]) -> None:
    """Two vendor rows landing on one buyer line.

    This is the quiet one. It is not a bad parse and not an obviously wrong
    match — it is two plausible matches competing, and its real cost is
    invisible: the OTHER line silently ends up with no quote at all, and a
    system that only checks "did every row get matched" reports success.

    Nova's schedule has two 450x350 fitments distinguished only by a cell count
    the label omits. Neither match is wrong on its face. Both are uncertain, and
    both belong in front of a human.
    """
    seen: dict[int, list[ExtractedQuoteLine]] = {}
    for m in matched:
        if m.line_no is not None:
            seen.setdefault(m.line_no, []).append(m)
    for line_no, group in seen.items():
        if len(group) < 2:
            continue
        for m in group:
            m.match_confidence = round(min(m.match_confidence, 0.45), 3)
            others = [g.vendor_label for g in group if g is not m]
            m.match_rationale = (
                f"AMBIGUOUS: {len(group)} rows in this quote match line {line_no} "
                f"equally well ({', '.join(others)}). One of them belongs to a "
                f"different line, which is now unquoted. " + (m.match_rationale or ""))


def _self_test() -> int:
    from extract.base import get_extractor
    from contracts.extraction import SourceDoc
    gt = GroundTruth.model_validate(
        json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8")))
    ex = get_extractor("fixture")

    total = correct = 0
    print()
    for sub in gt.submissions:
        vid = sub.vendor.vendor_id
        raw = ex.extract(SourceDoc(doc_id=f"{vid}-quote", vendor_id=vid, path="",
                                   kind=sub.vendor.reply_format, role="quote"))
        matched = match_submission(raw, gt)
        truth = {q.line_no for q in sub.line_quotes}
        got = {m.line_no for m in matched if m.line_no}
        hit = len(truth & got)
        total += len(truth); correct += hit
        lo = [m for m in matched if m.match_confidence < 0.82]
        print(f"  {sub.vendor.name:34s} {len(raw.lines):2d} raw rows -> "
              f"{len(matched):2d} matched   {hit:2d}/{len(truth)} correct   "
              f"{len(lo):2d} below threshold")
    print(f"\n  match accuracy {correct}/{total} = {correct/total:.1%}\n")

    print("  Ganesh quotes in INCHES against a tender written in mm:\n")
    raw = ex.extract(SourceDoc(doc_id="g", vendor_id="ganesh", path="", kind="image",
                               role="quote"))
    for rl in raw.lines[:4]:
        no, conf, why = match_line(rl, gt.rfx)
        print(f"    {rl.vendor_label:26s} -> line {no}  conf {conf:.2f}   {why}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--self-test", action="store_true")
    raise SystemExit(_self_test() if p.parse_args().self_test else 0)
