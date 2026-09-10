"""
Render every vendor document from data/ground_truth.json.

The documents are PROJECTIONS of the ground truth, which is what makes the eval
gold set free: extraction is scored against the thing the documents were made
from, not against 560 cells somebody labelled by hand afterwards.

Run:  python -m tools.render_all
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.quote import GroundTruth
from tools import render_docx, render_email, render_pdf, render_photo, render_xlsx

ROOT = Path(__file__).resolve().parent.parent
GT_PATH = ROOT / "data" / "ground_truth.json"
OUT = ROOT / "data" / "generated"
ATT = ROOT / "data" / "attachments"


def load() -> GroundTruth:
    return GroundTruth.model_validate(json.loads(GT_PATH.read_text(encoding="utf-8")))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ATT.mkdir(parents=True, exist_ok=True)
    gt = load()

    produced: list[tuple[str, Path]] = []
    produced.append(("Shakti  · XLSX  · own template, 2 sheets", render_xlsx.render(gt, OUT)))
    produced.append(("Nova    · PDF   · letterhead, footnote discount", render_pdf.render(gt, OUT)))
    produced.append(("Meridian· DOCX  · commercials in prose, USD", render_docx.render(gt, OUT)))
    produced.append(("Ganesh  · JPG   · rate card, photographed", render_photo.render(gt, OUT)))
    produced.append(("Apex    · EML   · four lines of email", render_email.render(gt, OUT)))

    render_email.render_questionnaire_sidecars(gt, OUT)

    # attachments
    produced.append(("  attach· PDF   · Nova ISO 9001 (EXPIRED 31-03-2026)",
                     render_pdf.render_nova_iso_certificate(ATT)))
    produced.append(("  attach· PDF   · Apex FY26 rate contract",
                     render_pdf.render_apex_prior_contract(gt, ATT)))
    produced.append(("  attach· PDF   · Meridian burst test report",
                     render_pdf.render_simple_attachment(
                         ATT, "meridian_test_report.pdf",
                         "Laboratory Test Report",
                         "Meridian Packaging International — In-house Laboratory, Chennai",
                         ["Report no. MPI/LAB/2026/0771 &nbsp;·&nbsp; Date 28 August 2026",
                          "<b>Test method:</b> TAPPI T810 om-11, bursting strength of corrugated board.",
                          "<b>Specimen:</b> 5-ply BC flute, 180 gsm machine-finished kraft liner.",
                          "<b>Result:</b> mean bursting strength 1,400 kPa across ten specimens "
                          "(range 1,352 to 1,461 kPa), conditioned at 23°C and 50% RH.",
                          "<b>Note:</b> This result is not directly comparable to an Edge Crush "
                          "Test value expressed in kN/m. The two methods measure different "
                          "failure modes and no general conversion exists between them."])))
    produced.append(("  attach· PDF   · Shakti capacity statement",
                     render_pdf.render_simple_attachment(
                         ATT, "shakti_capacity_statement.pdf",
                         "Statement of Plant Capacity",
                         "Shakti Packaging Pvt Ltd — Plot 44, MIDC Bhiwandi",
                         ["Installed converting capacity is 900 tonnes per month across one "
                          "corrugator and four converting lines.",
                          "The unit operates two shifts, extendable to three at 21 days notice.",
                          "We operate a single manufacturing location. No secondary plant or "
                          "documented disaster-recovery arrangement is currently in place."])))
    produced.append(("  attach· PDF   · Ganesh Udyam certificate",
                     render_pdf.render_simple_attachment(
                         ATT, "ganesh_udyam_certificate.pdf",
                         "Udyam Registration Certificate",
                         "Ministry of Micro, Small and Medium Enterprises, Government of India",
                         ["<b>Udyam registration number:</b> UDYAM-MH-19-0044821",
                          "<b>Name of enterprise:</b> Ganesh Boxes &amp; Cartons",
                          "<b>Type of enterprise:</b> Micro",
                          "<b>Major activity:</b> Manufacturing — corrugated fibreboard containers",
                          "<b>Date of Udyam registration:</b> 14 September 2021",
                          "<b>Date of incorporation:</b> 02 June 2009"])))

    print(f"\nrendered from {GT_PATH.name}\n")
    for note, p in produced:
        size = p.stat().st_size
        rel = p.relative_to(ROOT)
        print(f"  {note:52s} {str(rel):58s} {size/1024:8.1f} KB")
    print(f"\n  {len(list(OUT.iterdir()))} files in data/generated, "
          f"{len(list(ATT.iterdir()))} in data/attachments\n")


if __name__ == "__main__":
    main()
