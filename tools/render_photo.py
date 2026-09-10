"""
Ganesh Boxes & Cartons — a printed rate card, photographed at an angle on a phone.

This is not a simulated hard case, it is a real one. Tier-2 and tier-3 Indian
converters run on WhatsApp: the rate card is printed in April, the sales rep
photographs it on a desk, and that is what arrives. In a mid-market corrugated
panel it is roughly a third of the responses.

Traps rendered here, all of which have to be REAL because the low-confidence
extraction they produce has to be real:
  - every rate is per 100 pieces, where the buyer asked per piece
  - Indian digit grouping in the annual value column (7,03,68,000 not 70,368,000)
  - two lines revised in pen over the printed rate, months after printing
  - one row falls under the shadow of the photographer, partially occluded
  - perspective distortion, uneven lighting, phone-camera JPEG artefacts

Pipeline: render clean card -> pen annotations -> perspective warp -> desk
background -> lighting gradient and shadow -> blur -> JPEG compression.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from contracts.quote import GroundTruth
from tools.labels import ganesh as label

SEED = 4471
CARD_W, CARD_H = 1500, 2050

FONTS = {
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "reg": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "monob": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "pen": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
}
INK = (28, 28, 30)
PEN = (24, 48, 132)          # blue ballpoint


def f(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS[name], size)


def indian_group(n: int) -> str:
    """1,20,000 — not 120,000. A naive locale-blind parser reads this as 120."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


# ---------------------------------------------------------------------------
# 1. the printed card
# ---------------------------------------------------------------------------

def _draw_card(gt: GroundTruth) -> tuple[Image.Image, list[tuple[int, float, float]]]:
    sub = next(s for s in gt.submissions if s.vendor.vendor_id == "ganesh")
    lines = {l.line_no: l for l in gt.rfx.lines}

    img = Image.new("RGB", (CARD_W, CARD_H), (252, 251, 247))
    d = ImageDraw.Draw(img)

    # header block
    d.rectangle([0, 0, CARD_W, 190], fill=(232, 96, 40))
    d.text((70, 48), "GANESH BOXES & CARTONS", font=f("bold", 52), fill=(255, 255, 255))
    d.text((72, 112), "Gala 12, Morivali MIDC, Ambernath (W), Thane 421505",
           font=f("reg", 22), fill=(255, 236, 226))
    d.text((72, 144), "Ph 0251-2601188  ·  GSTIN 27ADQPG4482N1ZS  ·  Udyam-MH-19-0044821",
           font=f("reg", 20), fill=(255, 236, 226))

    d.text((70, 230), "RATE CARD  —  EFFECTIVE 01 APRIL 2026", font=f("bold", 34), fill=INK)
    d.text((70, 282), "ALL RATES ARE PER 100 PIECES.  EX-WORKS AMBERNATH.  GST EXTRA.",
           font=f("bold", 22), fill=(150, 40, 30))
    d.text((70, 316), "Quotation against enquiry " + gt.rfx.rfx_id + "   Dated 31-08-2026",
           font=f("reg", 21), fill=(90, 90, 94))

    # table header
    y = 372
    cols = [(70, "SR"), (150, "ITEM"), (720, "QTY P.A."), (960, "RATE / 100"), (1240, "ANNUAL VALUE")]
    d.rectangle([60, y, CARD_W - 60, y + 46], fill=(238, 236, 230))
    d.line([60, y, CARD_W - 60, y], fill=(120, 120, 124), width=3)
    d.line([60, y + 46, CARD_W - 60, y + 46], fill=(120, 120, 124), width=3)
    for x, t in cols:
        d.text((x, y + 12), t, font=f("monob", 22), fill=INK)

    rng = random.Random(SEED)
    y += 62
    row_h = 58
    pen_rows: list[tuple[int, float, float]] = []   # (row_index, printed, revised)
    shadow_row_y = 0

    for i, q in enumerate(sub.line_quotes, start=1):
        l = lines[q.line_no]
        rate = q.rate or 0.0
        annual = int(rate / 100 * l.annual_qty)   # every rate on this card is per 100

        # Two lines were revised in pen when board moved in July.
        revised = None
        if i in (6, 14):
            revised = round(rate * rng.uniform(1.06, 1.11), 0)
            pen_rows.append((i, rate, revised))

        d.text((70, y), f"{i:02d}", font=f("mono", 24), fill=INK)
        d.text((150, y), label(l), font=f("mono", 24), fill=INK)
        d.text((720, y), indian_group(l.annual_qty), font=f("mono", 24), fill=INK)
        rate_txt = f"{rate:,.2f}"
        d.text((960, y), rate_txt, font=f("mono", 24), fill=INK)
        d.text((1240, y), indian_group(annual), font=f("mono", 24), fill=INK)
        d.line([60, y + row_h - 12, CARD_W - 60, y + row_h - 12], fill=(214, 212, 206), width=1)

        if i == 17:
            shadow_row_y = y
        if revised is not None:
            _pen_revision(d, 960, y, rate_txt, revised, rng)
        y += row_h

    y += 26
    d.line([60, y, CARD_W - 60, y], fill=(120, 120, 124), width=3)
    y += 22
    d.text((70, y), "PAYMENT 30 DAYS FROM INVOICE.  OFFER VALID 21 DAYS.",
           font=f("bold", 23), fill=INK)
    y += 38
    d.text((70, y), "MINIMUM ORDER 2000 NOS PER ITEM.  LEAD TIME 12 DAYS.",
           font=f("reg", 22), fill=INK)
    y += 38
    d.text((70, y), "BOARD 22 BF.  WE DO NOT SUPPLY 7 PLY EXPORT CARTONS OR SHEETS.",
           font=f("reg", 22), fill=INK)
    y += 70
    d.text((70, y), "For GANESH BOXES & CARTONS", font=f("reg", 22), fill=INK)
    _signature(d, 78, y + 44, rng)
    d.text((70, y + 122), "Prop.  M. G. Ganesh", font=f("reg", 20), fill=(90, 90, 94))

    return img, [(shadow_row_y, 0, 0)] if shadow_row_y else []


def _wobble_text(d: ImageDraw.ImageDraw, xy, text, font, fill, rng, jitter=2.4):
    """Per-glyph jitter, so it reads as written rather than typeset."""
    x, y = xy
    for ch in text:
        d.text((x + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter)),
               ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) * rng.uniform(0.94, 1.02)


def _wobble_line(d, x0, y0, x1, y1, fill, rng, width=4, segs=9):
    pts = []
    for i in range(segs + 1):
        t = i / segs
        pts.append((x0 + (x1 - x0) * t + rng.uniform(-2, 2),
                    y0 + (y1 - y0) * t + rng.uniform(-3, 3)))
    d.line(pts, fill=fill, width=width, joint="curve")


def _pen_revision(d, x, y, printed_txt, revised, rng):
    """Strike the printed rate, write the new one above it. The rate card was
    printed in April; two grades moved in July; the rep wrote over it rather
    than reprint."""
    w = d.textlength(printed_txt, font=f("mono", 24))
    _wobble_line(d, x - 6, y + 18, x + w + 6, y + 12, PEN, rng, width=4)
    _wobble_text(d, (x + w + 26, y - 6), f"{revised:,.0f}", f("pen", 30), PEN, rng)


def _signature(d, x, y, rng):
    pts = [(x, y + 30)]
    for i in range(1, 26):
        pts.append((x + i * 11 + rng.uniform(-3, 3),
                    y + 30 - 26 * np.sin(i / 2.6) + rng.uniform(-4, 4)))
    d.line(pts, fill=PEN, width=5, joint="curve")


# ---------------------------------------------------------------------------
# 2. photograph it
# ---------------------------------------------------------------------------

def _perspective_coeffs(src_quad, dst_quad):
    A, B = [], []
    for (u, v), (x, y) in zip(src_quad, dst_quad):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.lstsq(np.array(A, float), np.array(B, float), rcond=None)[0]


def _photograph(card: Image.Image, rng: random.Random) -> Image.Image:
    W, H = 1700, 2260

    # desk surface with grain
    desk = Image.new("RGB", (W, H), (176, 170, 160))
    noise = (np.random.default_rng(SEED).normal(0, 7, (H, W, 3)) + 0).astype(np.int16)
    desk = Image.fromarray(np.clip(np.array(desk).astype(np.int16) + noise, 0, 255).astype(np.uint8))
    desk = desk.filter(ImageFilter.GaussianBlur(1.1))

    card = card.resize((1360, 1860), Image.LANCZOS)
    cw, ch = card.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(card.convert("RGBA"), (170, 190))

    # The angle: held slightly off-axis, top edge further away. Kept modest on
    # purpose -- enough vertical drop across the width to be a real perspective
    # problem, not so much that a row's own figures drift into the next row's
    # baseline. Beyond about half a row height the table stops being hard and
    # starts being ambiguous, which is a different (and unfair) test.
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    dst = [(96, 44), (W - 54, 78), (W - 118, H - 66), (30, H - 104)]
    coeffs = _perspective_coeffs(src, dst)
    layer = layer.transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)

    # drop shadow under the sheet
    alpha = layer.split()[3]
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(18)).point(lambda a: int(a * 0.55)))
    desk.paste(Image.new("RGB", (W, H), (60, 56, 52)), (14, 20), shadow)
    desk.paste(layer.convert("RGB"), (0, 0), layer)

    img = desk
    gx, gy = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))

    # Window light falling from the upper left.
    light = 1.12 - 0.26 * gx - 0.13 * gy

    # The photographer's own shadow: a soft diagonal wedge cast across the sheet
    # by the arm holding the phone. It lands over one band of rows and takes
    # roughly half the contrast out of them. This is the occlusion that has to
    # be genuine -- the low-confidence extraction it produces is the honest
    # kind, not a number we degraded on purpose.
    edge = 0.70 - 0.16 * gx                       # the wedge runs slightly uphill
    band = np.clip((gy - edge) / 0.055, 0, 1) * np.clip((edge + 0.135 - gy) / 0.055, 0, 1)
    shadow = 1.0 - 0.46 * band

    field = np.clip(light * shadow, 0.30, 1.18)[:, :, None]
    img = Image.fromarray(
        np.clip(np.array(img).astype(np.float32) * field, 0, 255).astype(np.uint8))

    # Phone camera: mild optical blur, extra blur inside the shadow where the
    # sensor is starved, sensor noise, then lossy compression.
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    blurred = img.filter(ImageFilter.GaussianBlur(2.1))
    mask = Image.fromarray((band * 190).astype(np.uint8))
    img = Image.composite(blurred, img, mask)

    n = np.random.default_rng(SEED + 1).normal(0, 3.4, (H, W, 3))
    n += (np.random.default_rng(SEED + 2).normal(0, 7.5, (H, W, 3)) * band[:, :, None])
    img = Image.fromarray(
        np.clip(np.array(img).astype(np.float32) + n, 0, 255).astype(np.uint8))
    return img.rotate(-0.9, resample=Image.BICUBIC, expand=False, fillcolor=(150, 145, 136))


def render(gt: GroundTruth, out_dir: Path) -> Path:
    rng = random.Random(SEED)
    card, _ = _draw_card(gt)
    photo = _photograph(card, rng)
    out = out_dir / "ganesh_rate_card_photo.jpg"
    photo.save(out, "JPEG", quality=72, optimize=True)
    return out
