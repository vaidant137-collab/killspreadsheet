"""
Record a real extraction run; replay it in the demo.

This is a demo-risk decision before it is an engineering one.

A live demo that calls a model to parse five documents has five chances to fail
in front of someone: a rate limit, a timeout, a provider incident, a flaky
network in a meeting room. And it fails at the worst possible moment, because
extraction is the FIRST thing that runs.

It is also the least interesting thing to watch. Nobody wants to sit through
forty seconds of OCR; they want to ask the comparison questions.

So: run extraction for real, once, with the model. Save exactly what came back,
verbatim, with the run's provenance attached. The demo replays that. The AI loop
is genuinely real — you can show the recording, the timestamp, the model name
and the scorecard from that run — and the live part of the demo is the analyst,
which is the part worth watching and the part that benefits from being live.

This is the opposite of hardcoding an answer. Nothing is edited: a recorded run
includes its own errors, and the eval scorecard is computed from it.

    python -m pipeline --extractor model --record     # spend the money once
    python -m pipeline --extractor replay             # every run after that
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config import DATA
from contracts.extraction import RawSubmission, SourceDoc

RUNS = DATA / "extraction_runs"
LATEST = DATA / "extraction_latest.json"


class RecordingExtractor:
    """Wraps a real extractor and writes down what it returned."""

    def __init__(self, inner, model_name: str):
        self.inner = inner
        self.kind = inner.kind
        self.model_name = model_name

    def extract(self, doc: SourceDoc) -> RawSubmission:
        out = self.inner.extract(doc)
        RUNS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {"recorded_at": stamp, "model": self.model_name,
                  "extractor": type(self.inner).__name__, "doc": doc.model_dump(),
                  "submission": json.loads(out.model_dump_json())}
        (RUNS / f"{doc.vendor_id}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")
        _refresh_index()
        return out


class ReplayExtractor:
    """Returns a recorded run verbatim. Refuses rather than inventing one."""

    kind = "replay"

    def extract(self, doc: SourceDoc) -> RawSubmission:
        p = RUNS / f"{doc.vendor_id}.json"
        if not p.exists():
            raise RuntimeError(
                f"No recorded extraction for '{doc.vendor_id}'. Record one first:\n"
                f"    python -m pipeline --extractor model --record\n"
                f"or run the fixture path with EXTRACTOR=fixture.")
        rec = json.loads(p.read_text(encoding="utf-8"))
        return RawSubmission.model_validate(rec["submission"])


def _refresh_index() -> None:
    runs = []
    for p in sorted(RUNS.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        runs.append({"vendor_id": r["doc"]["vendor_id"], "model": r["model"],
                     "extractor": r["extractor"], "recorded_at": r["recorded_at"],
                     "lines": len(r["submission"]["lines"])})
    LATEST.write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")


def provenance() -> dict | None:
    """What the demo can truthfully say about where its numbers came from."""
    if not LATEST.exists():
        return None
    return json.loads(LATEST.read_text(encoding="utf-8"))
