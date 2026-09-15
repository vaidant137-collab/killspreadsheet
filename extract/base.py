"""
The extraction seam.

    extract(SourceDoc) -> RawSubmission

Five formats, five implementations, one contract. Swapping any of them for a
better parser, a fine-tuned model or a commercial OCR service changes nothing
upstream or downstream.

`config.EXTRACTOR = "fixture"` replays known-good output in place of the model,
which is what lets the whole pipeline run, and the matcher be exercised for
real, before any API key exists.
"""

from __future__ import annotations

import re
from typing import Protocol

from contracts.extraction import RawSubmission, SourceDoc

# Text that addresses the reader as an agent rather than describing goods.
# A supplier has both a financial motive and free-text access to our model.
INJECTION_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"ignore (?:all |any )?(?:previous|prior|earlier|above) instructions",
        r"disregard (?:all |any )?(?:previous|prior|the) (?:instructions|rules|system)",
        r"\bsystem\s*(?:prompt|message|note)\s*[:\-]",
        r"you are (?:now |an )?(?:a |an )?(?:ai|assistant|language model)",
        r"(?:rank|score|mark|treat) (?:this|our|us)(?: vendor)? (?:as )?(?:first|lowest|best|highest)",
        r"mark (?:all )?(?:competitor|other vendors?)('|’)?s? (?:prices? )?(?:as )?unverified",
        r"do not (?:report|show|mention|disclose) this",
    )
]


def scan_for_injection(text: str) -> list[str]:
    """Find, log, and surface. Never silently drop — a supplier who tried this
    is something the buyer should know about."""
    hits: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        for pat in INJECTION_PATTERNS:
            if pat.search(s):
                hits.append(s[:300])
                break
    return hits


class Extractor(Protocol):
    kind: str

    def extract(self, doc: SourceDoc) -> RawSubmission: ...


def get_extractor(kind: str, mode: str | None = None):
    """fixture -> replay known-good output, no key needed
       replay  -> return a RECORDED real run, verbatim
       model   -> call the model now
       record  -> call the model now AND save what it returned"""
    from config import EXTRACTOR
    mode = mode or EXTRACTOR

    if mode == "fixture":
        from extract.fixture import FixtureExtractor
        return FixtureExtractor()
    if mode == "replay":
        from extract.recorded import ReplayExtractor
        return ReplayExtractor()

    from extract import docx_x, email_x, image_x, pdf_x, xlsx_x
    inner = {"xlsx": xlsx_x.XlsxExtractor, "pdf": pdf_x.PdfExtractor,
             "docx": docx_x.DocxExtractor, "image": image_x.ImageExtractor,
             "email": email_x.EmailExtractor}[kind]()
    if mode == "record":
        from extract.recorded import RecordingExtractor
        from llm.providers import get_client
        c = get_client("extract")
        return RecordingExtractor(inner, model_name=f"{c.name}:{c.model}")
    return inner
