"""
What is still missing from each vendor, and what asking would be worth.

The system's honest failure, stated everywhere else in this repo, is that seven
cells could not be derived and are shown as gaps. That is the right thing to do
with a number nobody can compute — and it is only half a product. A buyer
looking at a gap does not admire the refusal. They write to the vendor.

So this is the other half: for each vendor, what a follow-up would ASK for, and
what it would be worth if they answered. Worth is the number that decides
whether the mail is sent at all — six cells on 1.4 crore of annual spend is a
phone call, one cell on forty thousand rupees is not.

Every item here is derived from stored cells and the questionnaire. No model:
"ask them about X" is a claim about the data, and a model inventing one would
send a buyer's name to a supplier over nothing.
"""

from __future__ import annotations

from contracts.quote import GroundTruth
from contracts.normalized import CellState, NormalisedLine


# Every value here reads correctly after the word "the" — the ask is composed
# as "the <this> for N lines", and "the a rate per kilogram for 7 lines" went
# out on screen before anybody read it aloud.
_PLAIN = {"unit_weight_g": "finished weight per piece",
          "conversion rule per_piece -> kg": "finished weight per piece"}


def _plain(fact: str) -> str:
    """Say it the way a buyer would write it to a supplier."""
    return _PLAIN.get(fact, fact.replace("_", " "))


def gaps_for(gt: GroundTruth, rows: list[NormalisedLine]) -> list[dict]:
    """One entry per vendor who has something worth asking about."""
    lines = {l.line_no: l for l in gt.rfx.lines}
    out = []

    for sub in gt.submissions:
        vid = sub.vendor.vendor_id
        asks: list[dict] = []

        # 1. Cells that could not be derived at all. The most valuable ask in
        #    the system, because each one is a line the buyer cannot price.
        unresolved = [r for r in rows
                      if r.vendor_id == vid and r.state == CellState.UNRESOLVED]
        if unresolved:
            facts = sorted({r.missing_fact.split(" for ")[0] for r in unresolved
                            if r.missing_fact})
            worth = sum((lines[r.line_no].annual_qty if r.line_no in lines else 0)
                        for r in unresolved)
            asks.append({
                "kind": "unresolved",
                "what": (f"the {_plain(facts[0])} for "
                         f"{len(unresolved)} line{'' if len(unresolved) == 1 else 's'}"
                         if facts else f"{len(unresolved)} unpriceable lines"),
                "lines": sorted(r.line_no for r in unresolved),
                "why": ("Quoted per kilogram against a schedule in pieces. "
                        "Without the finished weight there is no price, and "
                        "no assumption we make here is theirs."),
                "units_at_stake": worth})

        # 2. Lines they never quoted. Sometimes deliberate, sometimes an
        #    oversight, and the difference is one email.
        quoted = {q.line_no for q in sub.line_quotes}
        missing = [n for n in lines if n not in quoted]
        if missing:
            asks.append({
                "kind": "no_quote",
                "what": f"a rate for {len(missing)} line"
                        f"{'' if len(missing) == 1 else 's'} they did not price",
                "lines": sorted(missing),
                "why": "A blank is useful, but only once we know it is deliberate.",
                "units_at_stake": sum(lines[n].annual_qty for n in missing)})

        # 3. A gating answer that failed, or an evidence file that contradicts
        #    it. This is the ask that can change who is allowed to win.
        for a in sub.questionnaire:
            q = next((x for x in gt.rfx.questionnaire if x.q_no == a.q_no), None)
            if q is None or not q.gating:
                continue
            if a.contradicted_by_evidence:
                asks.append({
                    "kind": "contradiction",
                    "what": f"evidence for question {a.q_no} that matches the answer",
                    "lines": [],
                    "why": (f"They answered “{a.answer[:60]}” and the attached "
                            f"file says otherwise. A current document would "
                            f"settle it either way."),
                    "units_at_stake": 0})

        # 4. A minimum order that blocks lines they otherwise win.
        moq = sub.vendor.moq_pieces or 0
        blocked = [n for n, l in lines.items()
                   if moq and l.annual_qty < moq and n in quoted]
        if blocked:
            asks.append({
                "kind": "moq",
                "what": f"a small-lot rate below their {moq:,}-piece minimum",
                "lines": sorted(blocked),
                "why": (f"{len(blocked)} scheduled lines are below their minimum, "
                        f"so the rate they quoted was never valid at our volume."),
                "units_at_stake": sum(lines[n].annual_qty for n in blocked)})

        if asks:
            out.append({"vendor_id": vid, "vendor": sub.vendor.name,
                        "asks": asks,
                        "units_at_stake": sum(a["units_at_stake"] for a in asks)})

    out.sort(key=lambda v: -v["units_at_stake"])
    return out


def compose_followup(gt: GroundTruth, entry: dict) -> dict:
    """The mail itself. Composed from the gaps, not written by a model."""
    lines = {l.line_no: l for l in gt.rfx.lines}
    body = [f"Dear {entry['vendor'].split()[0]} team,", "",
            f"Thank you for your quotation against {gt.rfx.rfx_id}. Before we "
            f"can compare it line for line we need the following:", ""]
    n = 0
    for a in entry["asks"]:
        n += 1
        body.append(f"{n}. {a['what'][0].upper()}{a['what'][1:]}.")
        if a["lines"]:
            body.append("   Lines: " + ", ".join(
                f"{no} ({lines[no].code})" for no in a["lines"][:8]
                if no in lines) + ("" if len(a["lines"]) <= 8 else ", …"))
        body.append(f"   {a['why']}")
        body.append("")
    body += ["Everything else in your quotation stands and does not need to be "
             "resent.", "",
             "Regards", "Procurement", gt.rfx.buyer_org]
    return {"vendor_id": entry["vendor_id"], "to": entry["vendor"],
            "subject": f"Re: {gt.rfx.rfx_id} — further information needed",
            "body": "\n".join(body),
            "asks": [a["what"] for a in entry["asks"]]}
