"""
How each vendor names the buyer's lines.

This is the matching problem, made concrete. No vendor uses the buyer's line
code. They use their own conventions, their own abbreviations, their own
column order. Getting Rs 42/kg out of a document is easy; knowing which of the
buyer's thirty lines it belongs to is the part that breaks in production.

A wrong match here is the worst failure in the system: the extraction was
perfect, the number is plausible, and nobody finds out until goods receipt.
"""

from __future__ import annotations

from contracts.rfx import BoxStyle, RfxLine

PLY_WORD = {2: "TWO", 3: "THREE", 5: "FIVE", 7: "SEVEN"}


def _dims(l: RfxLine, sep: str = "x") -> str:
    d = l.dims
    if d.height_mm is None:
        return f"{d.length_mm}{sep}{d.width_mm}"
    return f"{d.length_mm}{sep}{d.width_mm}{sep}{d.height_mm}"


def shakti(l: RfxLine) -> str:
    """Terse shop-floor naming, print spec folded into the description."""
    if l.style == BoxStyle.SHEET:
        return f"{l.ply} Ply Sheet {_dims(l)} - {l.liner_gsm}gsm"
    if l.style == BoxStyle.PAD:
        return f"Layer Pad {l.ply}Ply {_dims(l)}"
    if l.style == BoxStyle.PARTITION:
        return f"Partition {_dims(l)} {'4cell' if '4CELL' in l.code else ('6cell' if '6CELL' in l.code else 'cap+tray')}"
    p = {"plain": "", "1-col flexo": " 1col", "2-col flexo": " 2col"}[l.print_spec]
    kind = "Mailer" if l.style == BoxStyle.DIECUT_0427 else "RSC"
    return f"{l.ply} Ply {kind} {_dims(l)}{p}"


def nova(l: RfxLine) -> str:
    """Formal, upper case, spaced dimensions, BF quoted in the description."""
    if l.style == BoxStyle.SHEET:
        return f"CORRUGATED SHEET {l.ply}P {_dims(l, ' X ')} MM {l.bursting_factor}BF"
    if l.style == BoxStyle.PAD:
        return f"LAYER PAD {l.ply}P {_dims(l, ' X ')} MM"
    if l.style == BoxStyle.PARTITION:
        return f"PARTITION / FITMENT {_dims(l, ' X ')} MM"
    kind = "EXPORT CARTON" if l.style == BoxStyle.HSC_0203 else "CORRUGATED CASE"
    return f"{kind} {l.ply}P {_dims(l, ' X ')} MM {l.bursting_factor}BF"


def meridian(l: RfxLine) -> str:
    """Own SKU code plus a short marketing description. The code looks
    authoritative and matches nothing."""
    return f"MPI-{l.ply}{'S' if l.style == BoxStyle.SHEET else 'B'}-{l.dims.length_mm}{l.dims.width_mm}"


def meridian_desc(l: RfxLine) -> str:
    if l.style == BoxStyle.SHEET:
        return f"{PLY_WORD[l.ply]}-PLY SHEET, {_dims(l, ' x ')} mm"
    if l.style in (BoxStyle.PAD, BoxStyle.PARTITION):
        return f"FITMENT, {_dims(l, ' x ')} mm"
    return (f"{PLY_WORD[l.ply]}-PLY CASE, {_dims(l, ' x ')} mm, "
            f"{l.liner_gsm} gsm liner")


def _inches(l: RfxLine) -> str:
    """Millimetres to rounded whole inches, the way a small converter writes it.

    450 x 350 x 300 mm becomes 18X14X12. The rounding is lossy and it is applied
    by the supplier before the buyer ever sees it, so matching back to the
    tender's millimetre spec means tolerating up to ~12 mm of drift per axis.
    Confirmed convention: IndiaMART listings quote "16x12x10 inches",
    "12x10x8 inch", "7.00 X 5.00 X 4.25 Inches".
    """
    d = l.dims
    vals = [d.length_mm, d.width_mm] + ([d.height_mm] if d.height_mm else [])
    return "X".join(str(round(v / 25.4)) for v in vals)


def ganesh(l: RfxLine) -> str:
    """A printed rate card. All caps, no spaces, heavily abbreviated — and
    dimensions in INCHES, because that is what the trade actually does."""
    if l.style == BoxStyle.PAD:
        return f"PAD {_inches(l)}"
    if l.style == BoxStyle.PARTITION:
        # Two of the buyer's lines are 450x350 fitments. Ganesh distinguishes
        # them with a suffix that is easy to miss and easy to mis-read -- which
        # is realistic, and should surface as a low-confidence MATCH rather
        # than a low-confidence extraction.
        if "4CELL" in l.code:
            return f"PARTN {_inches(l)} 4C"
        if "6CELL" in l.code:
            return f"PARTN {_inches(l)} 6C"
        return f"CAP+TRAY {_inches(l)}"
    if l.style == BoxStyle.DIECUT_0427:
        return f"{l.ply}PLY DIECUT {_inches(l)}"
    # "Double Wall 3 Ply" is a real listing, and it contradicts itself: 3-ply is
    # single wall by definition. Real vendor data is not merely unstructured,
    # it is wrong — and a system that trusts a stated spec inherits the error.
    if l.ply == 3 and l.line_no in (2, 4):
        return f"DBL WALL 3PLY {_inches(l)}"
    return f"{l.ply}PLY {_inches(l)}"


LABELLERS = {
    "shakti": shakti,
    "nova": nova,
    "meridian": meridian_desc,
    "ganesh": ganesh,
}
