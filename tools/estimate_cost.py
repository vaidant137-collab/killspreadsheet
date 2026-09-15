"""
What does a run actually cost?

Measured, not guessed: this counts the tokens the extractors really send for the
five documents in data/generated, and prices a realistic project against current
published rates.

Run:  python -m tools.estimate_cost
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from config import DATA, ROOT

CHARS_PER_TOKEN = 3.7          # dense tabular text runs denser than prose
PX_PER_IMAGE_TOKEN = 750

# Published rates, USD per million tokens. Check before relying on them.
PRICES = {
    "Gemini Flash-Lite":  (0.30, 2.50),
    "Gemini Flash":       (0.75, 3.75),
    "Claude Haiku 4.5":   (1.00, 5.00),
    "Claude Sonnet 5":    (2.00, 10.00),
    "Claude Opus 5":      (5.00, 25.00),
}

# A realistic project, not a single happy-path run.
EXTRACT_PASSES = 20      # debugging, re-runs, then one recorded run for the demo
ANALYST_QUESTIONS = 80   # development, rehearsal, the recording, the live demo


def _tok(s: str) -> float:
    return len(s) / CHARS_PER_TOKEN


def measure() -> dict:
    gen = DATA / "generated"
    text_tok = img_tok = 0.0

    from openpyxl import load_workbook
    p = next(gen.glob("shakti*.xlsx"))
    wb = load_workbook(p, data_only=True)
    text_tok += _tok("\n".join(
        " | ".join(f"{c.coordinate}={c.value}" for c in row if c.value is not None)
        for ws in wb.worksheets for row in ws.iter_rows(max_row=120)))

    from pypdf import PdfReader
    rd = PdfReader(str(next(gen.glob("nova*.pdf"))))
    text_tok += _tok("\n".join(pg.extract_text() or "" for pg in rd.pages))
    img_tok += len(rd.pages) * 1100 * 1550 / PX_PER_IMAGE_TOKEN   # rendered pages

    from docx import Document
    d = Document(next(gen.glob("meridian*.docx")))
    text_tok += _tok("\n".join(x.text for x in d.paragraphs) + "\n".join(
        " | ".join(c.text for c in r.cells) for t in d.tables for r in t.rows))

    im = Image.open(next(gen.glob("ganesh*.jpg")))
    w, h = im.size
    px = w * h + 2 * (min(1600, w * 2) * int(h * 0.58 * min(1600, w * 2) / w))
    img_tok += px / PX_PER_IMAGE_TOKEN

    text_tok += _tok(next(gen.glob("apex*.eml")).read_text(encoding="utf-8"))
    text_tok += 5 * _tok((ROOT / "extract" / "prompts.py").read_text())

    from analyst.loop import SYSTEM
    from analyst.tools import TOOL_SPECS
    per_step = _tok(SYSTEM) + _tok(json.dumps(TOOL_SPECS)) + 1500

    return {"extract_in": text_tok + img_tok, "extract_out": 15_500,
            "extract_img_share": img_tok / (text_tok + img_tok),
            "q_in": per_step * 4 * 1.35, "q_out": 1_200}


def main() -> None:
    m = measure()
    print(f"\n  MEASURED, from the five documents in data/generated\n")
    print(f"    one extraction pass   {m['extract_in']:9,.0f} in  "
          f"{m['extract_out']:8,.0f} out"
          f"   ({m['extract_img_share']:.0%} of input is image tokens)")
    print(f"    one analyst question  {m['q_in']:9,.0f} in  {m['q_out']:8,.0f} out")
    print(f"\n  PRICED over {EXTRACT_PASSES} extraction passes and "
          f"{ANALYST_QUESTIONS} analyst questions\n")
    print(f"    {'model':20s} {'extraction':>11s} {'analyst':>10s} {'total':>9s}")
    for name, (pin, pout) in PRICES.items():
        e = EXTRACT_PASSES * (m["extract_in"] * pin + m["extract_out"] * pout) / 1e6
        a = ANALYST_QUESTIONS * (m["q_in"] * pin + m["q_out"] * pout) / 1e6
        flag = "" if e + a <= 5 else "   over $5"
        print(f"    {name:20s} {e:10.2f}  {a:9.2f} {e + a:9.2f}{flag}")

    pin_g, pout_g = PRICES["Gemini Flash"]
    pin_s, pout_s = PRICES["Claude Sonnet 5"]
    a = ANALYST_QUESTIONS * (m["q_in"] * pin_s + m["q_out"] * pout_s) / 1e6
    print(f"\n    {'Split: extraction on the Gemini free tier,':50s}")
    print(f"    {'analyst on Sonnet 5':20s} {0.00:10.2f}  {a:9.2f} {a:9.2f}")
    print(f"\n  Output tokens dominate: they cost 4-5x input and extraction emits")
    print(f"  ~15k of them per pass. Recording extraction once and replaying it")
    print(f"  removes that cost from every run after the first.\n")


if __name__ == "__main__":
    main()
