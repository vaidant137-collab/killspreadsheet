"""
Render round two: the reply each vendor sends when the buyer writes back.

Same principle as every other document here — a PROJECTION of the ground truth,
so the extractor's job is to get back to something that already exists and the
eval gold set stays free. These are plain emails because that is what a
clarification actually arrives as: nobody fills in a form to tell you a box
weighs 412 grams.

Run:  python -m tools.render_clarify
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.quote import GroundTruth

ROOT = Path(__file__).resolve().parent.parent
GT_PATH = ROOT / "data" / "ground_truth.json"
OUT = ROOT / "data" / "generated"

FROM = {
    "apex": "Rakesh Shetty <rakesh@apexpackwell.in>",
    "nova": "Priya Menon <priya.menon@novacorrugators.com>",
    "ganesh": "Ganesh Boxes <ganeshboxes.ambernath@gmail.com>",
    "meridian": "S. Rajagopal <rajagopal@meridianpkg.com>",
    "shakti": "Shakti Packaging <sales@shaktipack.in>",
}


def render_one(gt: GroundTruth, vendor_id: str, out_dir: Path) -> Path | None:
    c = next((x for x in gt.clarifications if x.vendor_id == vendor_id), None)
    if c is None:
        return None
    lines = [
        f"From: {FROM.get(vendor_id, vendor_id)}",
        "To: purchase.category@nandancp.in",
        f"Date: {c.received_at}",
        f"Subject: Re: {gt.rfx.rfx_id} - further information",
        "",
        c.reply_text,
    ]
    out = out_dir / f"{vendor_id}_clarification.eml"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gt = GroundTruth.model_validate(json.loads(GT_PATH.read_text(encoding="utf-8")))
    made = []
    for c in gt.clarifications:
        p = render_one(gt, c.vendor_id, OUT)
        if p:
            made.append((c.vendor_id, p))
    print(f"\nrendered {len(made)} clarification replies\n")
    for vid, p in made:
        print(f"  {vid:10s} {p.name:34s} {p.stat().st_size:5d} bytes")
    print()


if __name__ == "__main__":
    main()
