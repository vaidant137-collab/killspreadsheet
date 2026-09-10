"""
Apex Packwell — the incumbent's four-line email.

This is the brief's own example, and it is the most interesting document in the
set because it fails in three different ways at once:

  - "Rs 42/kg for the 5-ply, 38 for the 3-ply" prices BOARD, but the buyer buys
    PIECES. Converting needs a box weight. The buyer has weights for lines they
    have bought before and none for the six introduced this year, so six lines
    are genuinely unresolvable — and the system must say so rather than average
    a weight and quietly rank Apex fourth.
  - "rest same as last year" is a POINTER, not a price. It resolves only against
    the FY26 rate contract, which is attached.
  - "freight extra" leaves the Incoterm undeclared, and validity is never stated
    at all.

Nothing here is malformed. This is just how incumbents quote, because they
assume you have the file — and you do, it is simply in a different system than
the one you are comparing in.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.quote import GroundTruth

BODY = """From: Rakesh Shetty <rakesh@apexpackwell.in>
To: purchase.category@nandancp.in
Cc: accounts@apexpackwell.in
Date: Tue, 2 Sep 2026 19:41:08 +0530
Subject: Re: RFX-2026-CORR-011 - Annual corrugated requirement FY27
Attachments: apex_rate_contract_fy26.pdf

Rakesh here.

Rs 42/kg for the 5-ply, 38 for the 3-ply, rest same as last year, freight extra.

Attaching last year's contract for your ready reference. Terms as before.

We have been supplying you for six years now, kindly consider.

Regards
Rakesh Shetty
Apex Packwell, Bhiwandi
98201 44712
"""


def render(gt: GroundTruth, out_dir: Path) -> Path:
    sub = next(s for s in gt.submissions if s.vendor.vendor_id == "apex")
    out = out_dir / "apex_reply.eml"
    out.write_text(BODY, encoding="utf-8")

    # The questionnaire came back separately, as it usually does — a reply to a
    # second email, in the body, unnumbered.
    q_lines = ["From: Rakesh Shetty <rakesh@apexpackwell.in>",
               "To: purchase.category@nandancp.in",
               "Date: Wed, 3 Sep 2026 11:12:44 +0530",
               "Subject: Re: RFX-2026-CORR-011 - vendor questionnaire",
               "", "Sir,", "", "As asked -", ""]
    for item, ans in zip(gt.rfx.questionnaire, sub.questionnaire):
        q_lines.append(f"{item.question}")
        q_lines.append(f"  {ans.answer}")
        q_lines.append("")
    q_lines += ["Regards", "Rakesh"]
    (out_dir / "apex_questionnaire_reply.eml").write_text("\n".join(q_lines), encoding="utf-8")
    return out


def render_questionnaire_sidecars(gt: GroundTruth, out_dir: Path) -> list[Path]:
    """Shakti, Nova, Meridian and Ganesh returned the questionnaire as a filled
    form. Kept as JSON-ish text rather than yet another format — the point of
    the demo is five *pricing* formats, and adding four more questionnaire
    formats would be padding rather than signal."""
    written = []
    for sub in gt.submissions:
        if sub.vendor.vendor_id == "apex":
            continue
        payload = {
            "vendor": sub.vendor.name,
            "rfx_id": gt.rfx.rfx_id,
            "responses": [
                {"q_no": a.q_no,
                 "question": next(q.question for q in gt.rfx.questionnaire if q.q_no == a.q_no),
                 "answer": a.answer,
                 "evidence": a.evidence_file}
                for a in sub.questionnaire
            ],
        }
        p = out_dir / f"{sub.vendor.vendor_id}_questionnaire.json"
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(p)
    return written
