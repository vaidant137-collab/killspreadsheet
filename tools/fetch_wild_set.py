"""
Fetch the WILD SET — genuinely real documents, downloaded from their publishers.

Why this is a separate set from the demo set
--------------------------------------------
The demo documents are generated, which is what makes the gold set free: they
are projections of data/ground_truth.json, so extraction can be scored without
anybody labelling anything. That property is worth a lot, and it is only
available for documents we made.

Real documents have no ground truth until a human writes one. So you cannot
have both a real corpus and a free gold set — and pretending otherwise is how
an extractor ends up quietly overfitted to the quirks of its own renderer.

The answer is two sets with two jobs:

    demo set   generated, ground truth free, drives the headline scorecard
    wild set   real, hand-labelled, small, answers "does this work on documents
               we did not make?"

A handful of labelled fields from the wild set is enough. If accuracy on the
demo set is 96% and accuracy on the wild set is 61%, the 96% was measuring the
renderer, not the extractor — and that is exactly the kind of thing worth
finding out before a live demo rather than during one.

Run:  python -m tools.fetch_wild_set
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WILD = ROOT / "data" / "wild"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Every URL below was read and verified before being listed. The "why" column is
# the reason the document is in the corpus at all — a wild set of things that
# merely exist teaches nothing.
MANIFEST = [
    {
        "name": "yojpack_product_catalogue.pdf",
        "url": "https://www.yojpack.com/YOJ-pack-kraft-Product-catalogue.pdf",
        "kind": "vendor catalogue",
        "why": "24 pages. Prices ARE present but in units no RFx line can consume — "
               "Rs 160/sq metre, Rs 850/pallet, Rs 10/piece. Most of the range is "
               "honeycomb board and paper pallets, not the corrugated boxes a buyer "
               "asking about corrugated boxes wants. MOQs sit inside marketing prose "
               "('5000-box minimum'). The signal-to-noise case.",
    },
    {
        "name": "trident_pbi_brochure.pdf",
        "url": "https://tridentpbi.in/trident-pbi-corrugated-box-manufacturer-brochure.pdf",
        "kind": "vendor brochure",
        "why": "No prices at all — so it is not a bid, however much it looks like a "
               "response. Carries a section headed 'OUR CERTIFICATIONS' with nothing "
               "underneath it: absence of evidence, laid out as though it were "
               "presence. Capacity stated twice in units that do not convert "
               "(90,000 boxes/day and 18,000 MT/year).",
    },
    {
        "name": "pramukh_packaging_brochure.pdf",
        "url": "https://www.pramukhpackagingindustries.com/brochure.pdf",
        "kind": "vendor brochure",
        "why": "~70% marketing. A corrugated company whose brochure lists BOPP tape and "
               "stretch film as its products. Extensive machinery detail with real model "
               "sizes, 31 named clients, and no pricing, lead times, MOQs or product "
               "specifications. The 'answers a question nobody asked' case.",
    },
    {
        "name": "walmart_corrugated_board_specification.pdf",
        "url": "https://www.fibrebox.org/assets/2025/09/"
               "Walmart_Corrugated-Board_Specifications_Automation_Packaging_Standards.pdf",
        "kind": "buyer specification",
        "why": "A real buyer-side board specification from a major retailer. Useful as "
               "the counterweight to the Indian tender: shows how the same category is "
               "specified under a different standards regime (ECT-led rather than "
               "bursting-factor-led), which is the comparability problem at country scale.",
    },
    {
        "name": "dcmsme_corrugated_paper_board_and_boxes.pdf",
        "url": "https://dcmsme.gov.in/Corrugated%20Paper%20Board%20&%20Boxes%20by%20CSS%20Rao.pdf",
        "kind": "reference",
        "why": "Government of India MSME technical reference on corrugated board and "
               "boxes. Ground truth for terminology, grades and Indian test standards — "
               "useful for checking that the demo dataset's vocabulary is right.",
    },
]


def fetch(entry: dict, dest: Path) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(entry["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
        if len(data) < 2048:
            return False, f"suspiciously small ({len(data)} bytes) — probably an error page"
        if entry["name"].endswith(".pdf") and not data[:5].startswith(b"%PDF"):
            return False, "not a PDF — the server returned something else"
        dest.write_bytes(data)
        return True, f"{len(data)/1024:.0f} KB"
    except Exception as e:                                  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    WILD.mkdir(parents=True, exist_ok=True)
    ok = failed = 0

    print(f"\nfetching {len(MANIFEST)} real documents into data/wild/\n")
    for e in MANIFEST:
        dest = WILD / e["name"]
        if dest.exists() and dest.stat().st_size > 2048:
            print(f"  · {e['name']:52s} already present, skipping")
            ok += 1
            continue
        good, note = fetch(e, dest)
        mark = "✓" if good else "✗"
        print(f"  {mark} {e['name']:52s} {note}")
        ok, failed = (ok + 1, failed) if good else (ok, failed + 1)

    (WILD / "MANIFEST.md").write_text(
        "# Wild set\n\n"
        "Real documents, downloaded from their publishers by `tools/fetch_wild_set.py`.\n"
        "Not redistributed with this repository — the fetcher pulls them on your machine.\n\n"
        "These are **not** part of the demo dataset and they have no free ground truth.\n"
        "They exist to answer one question: does extraction work on documents we did not\n"
        "make? Label a handful of fields by hand and score against those.\n\n"
        + "\n".join(
            f"## {e['name']}\n\n**{e['kind']}** · [source]({e['url']})\n\n{e['why']}\n"
            for e in MANIFEST),
        encoding="utf-8")

    print(f"\n  {ok} available, {failed} failed. Manifest written to data/wild/MANIFEST.md\n")
    if failed:
        print("  If every entry failed with 403 or a tunnel error, you are behind a proxy")
        print("  that blocks direct downloads — run this on a normal connection. A single")
        print("  failure is usually that publisher blocking automated requests.")
        print("  Either way: open the URL in a browser, save the file into data/wild/, and")
        print("  carry on. Nothing downstream cares how the file got there.\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
