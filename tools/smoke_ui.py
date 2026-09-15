"""
Drive the page. The Python suite cannot see any of this.

The scorecard, the seam tests and the adversarial set all sit behind the API,
and the API answered correctly through every failure this project has had. What
broke was the browser code in front of it: three functions called and never
defined, and a fourth writing to an element a redesign had removed. Two
exceptions, and between them the tabs, the RFx draft card, the co-pilot's first
reply and the comparison grid — the point of the screen — all rendered as
nothing, while every endpoint behind them returned the right answer.

`node --check` catches syntax and nothing else. A thrown exception in a boot
path leaves the static HTML on screen looking perfectly fine. So this starts the
real server, drives the real page with a real browser, and fails on any
uncaught exception or console error.

The co-pilot's own turn is exercised against a STUBBED event stream, not a live
model: what is being tested is whether the browser can render what the agent
emits, and paying for a model call to find out would make this too expensive to
run on every change — which is the same as not having it.

Run:  python -m tools.smoke_ui
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What the RFx co-pilot emits on its first turn. Shapes, not content — if
# contracts/blocks.py gains a field this stays valid; if the UI stops handling a
# block type, this fails.
STREAM = [
    {"kind": "status", "payload": "propose_default_rfx…"},
    {"kind": "block", "payload": {
        "type": "rfx_draft", "title": "RFx — draft",
        "fields": [{"label": "Payment terms", "value": "45 days from GRN",
                    "changes": "every landed cost is NPV-adjusted to this"}],
        "lines_included": 30, "lines_available": 30, "questions_included": 9,
        "gating": ["Q1 · ISO 9001"], "vendors": ["Apex"], "missing": [],
        "ready": True}},
    {"kind": "block", "payload": {
        "type": "choice", "key": "payment_terms", "title": "Payment terms",
        "multi": False, "allow_other": True, "other_hint": "e.g. 75 days",
        "options": [
            {"value": "30", "label": "30 days from GRN",
             "consequence": "2 vendors move up", "selected": False},
            {"value": "45", "label": "45 days from GRN",
             "consequence": "as quoted", "selected": True}]}},
    {"kind": "block", "payload": {"type": "text",
                                  "text": "Change what matters."}},
    {"kind": "done"},
]

STUB = """
window.__of = window.fetch; window.__asked = [];
// Intercept ONLY the analyst call, and hand everything else back with its
// arguments untouched. A wrapper that rebuilds the call as (u, o) mangles the
// forms it does not expect and issues a request for the string "null", which
// then shows up as a 404 this harness blames on the page.
window.fetch = function(u, o){
  if (typeof u === 'string' && u.includes('/api/ask')){
    try { window.__asked.push(JSON.parse(o.body).question); } catch(e){}
    const evs = window.__asked.length === 1 ? %s : [{"kind":"done"}];
    const enc = new TextEncoder(); let i = 0;
    return new Response(new ReadableStream({ async pull(c){
      if (i >= evs.length){ c.close(); return; }
      c.enqueue(enc.encode('data: ' + JSON.stringify(evs[i++]) + '\\n\\n'));
      await new Promise(r => setTimeout(r, 15)); }}), {status:200});
  }
  return window.__of.apply(this, arguments);
};
// Leave a primitive as the completion value. page.evaluate serialises whatever
// the last expression produced, and handing it a freshly assigned function sends
// it round the handle-serialisation path — which then issues a request of its
// own that this harness would report as the page's bug.
'stubbed';
""" % json.dumps(STREAM)


def _free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Checks:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def is_(self, ok: bool, name: str, detail: str = "") -> None:
        self.rows.append((bool(ok), name, detail))

    def eq(self, got, want, name: str) -> None:
        self.is_(got == want, name, f"got {got!r}, wanted {want!r}")

    def at_least(self, got: int, n: int, name: str) -> None:
        self.is_(got >= n, name, f"got {got}, wanted at least {n}")

    def report(self) -> int:
        bad = [r for r in self.rows if not r[0]]
        for ok, name, detail in self.rows:
            print(f"    [{'ok  ' if ok else 'FAIL'}]  {name}"
                  + (f"   — {detail}" if not ok and detail else ""))
        print(f"\n  {len(self.rows) - len(bad)} of {len(self.rows)} checks pass.\n")
        return 1 if bad else 0


async def run(port: int, c: Checks) -> None:
    from playwright.async_api import async_playwright

    url = f"http://127.0.0.1:{port}/"
    problems: list[str] = []

    def card(pg, key):
        return pg.locator(f'[data-card="{key}"]')

    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        pg.on("pageerror", lambda e: problems.append(f"uncaught: {e}"))
        # A 404 is reported by the console as "Failed to load resource" with no
        # URL attached, which is useless. Name the request. Only same-origin
        # failures are this page's problem: a blocked webfont host is a fact
        # about the network, and the stylesheet names a real fallback stack.
        pg.on("requestfailed", lambda r: problems.append(f"request failed: {r.url}")
              if r.url.startswith(url) else None)
        # 409 is this app saying "the RFx has not been issued", which is the
        # behaviour a check below deliberately provokes. Every other 4xx/5xx is
        # a bug.
        pg.on("response", lambda r: problems.append(
            f"HTTP {r.status}: {r.url}  [after {len(c.rows)} checks]")
              if r.status >= 400 and r.status != 409 and r.url.startswith(url)
              else None)

        async def draft():
            return (await pg.evaluate("fetch('/api/draft').then(r => r.json())"))["draft"]

        # ---- the empty page ------------------------------------------------
        import httpx
        httpx.post(f"{url}api/reset", timeout=10)
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(800)

        # Every element the script reaches for must exist. This is exactly the
        # shape of the bug that blanked the comparison grid: a renderer kept
        # writing to a header element a redesign had removed, threw, and took
        # the whole comparison half down with it. Cheap, and it covers the file
        # rather than only the paths this harness happens to walk.
        dangling = await pg.evaluate(r"""() => {
          const html = document.documentElement.outerHTML;
          const script = html.slice(html.indexOf("<scr" + "ipt"));
          const used = new Set();
          const res = [/\$\((?:"|')#([A-Za-z0-9_-]+)(?:"|')\)/g,
                       /getElementById\((?:"|')([A-Za-z0-9_-]+)(?:"|')\)/g];
          for (const re of res)
            for (const m of script.matchAll(re)) used.add(m[1]);
          return [...used].filter(id => !document.getElementById(id));
        }""")
        c.is_(not dangling, "every element the script reaches for exists",
              ", ".join(dangling))
        c.eq(await pg.locator("nav.tabs").count(), 0,
             "nothing is behind a tab — there are no tabs")

        # Nothing the vendors have not sent may reach the drafting screen, and
        # not just the pixels. The payload used to carry the finished
        # comparison, every qualification and the injection log while the buyer
        # was still writing the RFx; the page drew none of it, which made the
        # invariant hold by luck rather than by design.
        leaked = await pg.evaluate(r"""async () => {
          const names = ["Shakti", "Nova", "Apex", "Meridian", "Ganesh"];
          const out = [];
          for (const path of ["api/state", "api/catalogue", "api/draft"]) {
            const body = await fetch("/" + path).then(r => r.text());
            for (const n of names)
              if (body.includes(n + " saves") || body.includes(n + " costs")
                  || body.includes("removes " + n)) out.push(path + ": " + n);
            if (path === "api/state" && /"qualified"|"comparison"/.test(body))
              out.push(path + ": qualification/comparison");
          }
          return out;
        }""")
        c.is_(not leaked,
              "nothing a vendor has not sent reaches the drafting screen",
              "; ".join(leaked))

        # And the door, not only the markup. "The UI does not call it" is not a
        # property of the system.
        codes = await pg.evaluate(r"""async () => {
          const out = {};
          for (const p of ["comparison", "options", "memo", "reviews",
                           "assumptions", "summary", "gaps", "spend"])
            out[p] = (await fetch("/api/" + p)).status;
          return out;
        }""")
        c.is_(all(v == 409 for v in codes.values()),
              "endpoints that describe responses refuse before the RFx is issued",
              str(codes))
        c.at_least(await pg.locator("#suggest button").count(), 3,
                   "the empty page offers openers")

        # ---- step 1: the line schedule -------------------------------------
        c.eq(await pg.locator("#col .box").count(), 1,
             "one step is open at a time — the schedule comes first")
        c.eq(await card(pg, "items").locator("table.pick tbody tr").count(), 30,
             "thirty lines in the item master")
        c.eq(await card(pg, "items").locator("select.catsel option").count(), 5,
             "five categories, four of them honestly empty")
        d = await draft()
        c.eq(len(d["line_nos"]), 30,
             "an annual tender starts from the whole item master")

        row = card(pg, "items").locator("table.pick tbody tr").first
        await row.click(); await pg.wait_for_timeout(450)
        c.eq(len((await draft())["line_nos"]), 29,
             "unticking a line writes the draft, with no model call")
        await row.click(); await pg.wait_for_timeout(450)

        qty = card(pg, "items").locator("table.pick tbody input.qty").first
        await qty.fill("12345"); await qty.press("Enter")
        await pg.wait_for_timeout(600)
        c.eq((await draft())["qty_overrides"].get("1")
             or (await draft())["qty_overrides"].get(1), 12345,
             "a changed quantity is an override on the line, not an edit to the master")

        await card(pg, "items").locator(".bf button", has_text="Add a line").click()
        await card(pg, "items").locator(".addrow input.d").fill("Shelf-ready tray, 3-ply")
        await card(pg, "items").locator(".addrow input.q").fill("50000")
        await card(pg, "items").locator(".addrow button", has_text="Add").click()
        await pg.wait_for_timeout(700)
        d = await draft()
        c.eq(len(d["extra_lines"]), 1,
             "a line the buyer adds this year goes on the schedule")
        c.is_(await card(pg, "items").locator("table.pick tr.new").count() == 1,
              "and is marked as having no price history")

        await card(pg, "items").locator(".bf button", has_text="Continue").click()
        await pg.wait_for_timeout(600)
        c.is_("done" in (await card(pg, "items").get_attribute("class")),
              "finishing a step collapses it to one line")
        c.is_("31 lines" in await card(pg, "items").locator(".done-line").inner_text(),
              "and that line counts what is actually on the schedule",
              await card(pg, "items").locator(".done-line").inner_text())

        # ---- step 2: the vendors -------------------------------------------
        c.eq(await card(pg, "vendors").locator(".vcard").count(), 5,
             "five approved vendors")
        c.eq(len((await draft())["vendor_ids"]), 5, "all of them invited to start")
        await card(pg, "vendors").locator(".vcard").first.click()
        await pg.wait_for_timeout(450)
        c.eq(len((await draft())["vendor_ids"]), 4, "un-inviting one writes the list")
        await card(pg, "vendors").locator(".bf button", has_text="Invite all").click()
        await pg.wait_for_timeout(500)
        await card(pg, "vendors").locator(".bf button", has_text="Continue").click()
        await pg.wait_for_timeout(600)

        # ---- step 3: the questionnaire and the terms ------------------------
        qs = card(pg, "questions")
        c.eq(await qs.locator(".qrow").count(), 9, "nine questions on file")
        d = await draft()
        c.eq(sorted(d["gating_q_nos"]), [1, 7, 8],
             "the gates the template already had are carried over, not invented")
        await qs.locator(".qrow").nth(1).click(); await pg.wait_for_timeout(450)
        d = await draft()
        c.eq(len(d["question_nos"]), 8,
             "dropping a question sticks — it is not quietly put back")
        await qs.locator(".qrow").nth(7).click(); await pg.wait_for_timeout(450)
        d = await draft()
        c.is_(8 not in d["gating_q_nos"],
              "and a question you are not asking cannot disqualify anyone",
              str(d["gating_q_nos"]))
        await qs.locator(".qrow").nth(7).click(); await pg.wait_for_timeout(450)
        await qs.locator(".qrow").nth(7).locator(".gate").click()
        await pg.wait_for_timeout(450)

        await qs.locator(".terms button", has_text="30 days").click()
        await pg.wait_for_timeout(500)
        d = await draft()
        c.eq(d["payment_terms_days"], 30,
             "picking terms writes the field that re-prices every cell")
        c.is_("working capital" in await qs.locator(".consq").inner_text(),
              "and the card says what those terms cost, from last year's spend",
              await qs.locator(".consq").inner_text())
        c.is_((d["response_due"] or "") > time.strftime("%Y-%m-%d"),
              "responses are due in the future, not on the template's old date",
              str(d["response_due"]))
        await qs.locator(".bf button", has_text="Continue").click()
        await pg.wait_for_timeout(1200)

        # ---- step 4: the covering mail -------------------------------------
        # The buyer is about to write to five companies. What has to be in front
        # of them is the text that goes out and the list it goes to — not a note
        # saying a mail exists somewhere above.
        mail = card(pg, "mail")
        body = await mail.locator("textarea.mailbody").input_value()
        c.at_least(len(body), 400, "it is the whole mail, not a summary of it")
        n_q = len((await draft())["question_nos"])
        c.is_(f"{n_q} question" in body,
              "it asks for exactly the questions the buyer kept",
              f"expected {n_q} in the body")
        c.is_("disqualif" in body.lower(),
              "and says which answers end the submission")
        c.is_("minimum order" in body.lower() and "freight" in body.lower(),
              "and asks for the things the comparison actually needs")
        c.is_("to be confirmed" not in body,
              "with a real date on it")
        c.eq(await mail.locator(".stub").count(), 1,
             "the card says on its face that the send is stubbed")

        await mail.locator("textarea.mailbody").fill(body + "\n\nP.S. drawing rev C.")
        await mail.locator("textarea.mailbody").press("Tab")
        await pg.wait_for_timeout(600)
        d = await draft()
        c.is_("drawing rev C" in (d["mail_body"] or "") and not d["mail_approved"],
              "the buyer's own wording is what goes out, and it is not pre-approved")
        await mail.locator(".bf button", has_text="Recompose").click()
        await pg.wait_for_timeout(800)
        c.is_("drawing rev C" not in
              await mail.locator("textarea.mailbody").input_value(),
              "and they can get the composed version back")

        # ---- the co-pilot's turn, against a stubbed stream ------------------
        await pg.evaluate(STUB)
        await pg.fill("#q", "annual corrugated, back in two weeks")
        await pg.press("#q", "Enter")
        await pg.wait_for_timeout(1400)
        c.eq(await pg.locator(".turn .status", has_text="thinking").count(), 0,
             "the turn ends — it does not sit on 'thinking' for ever")
        c.at_least(await pg.locator(".choice .opt").count(), 2,
                   "a decision renders as options you click")
        c.is_("2 vendors move up" in await pg.locator(".choice").inner_text(),
              "each option carries its computed consequence")
        await pg.locator(".choice .opt", has_text="30 days").first.click()
        await pg.wait_for_timeout(900)
        c.eq((await draft())["payment_terms_days"], 30,
             "and a click writes the field itself, not a sentence about it")

        # ---- sending, and the round ----------------------------------------
        before = (await draft())["mail_approved"]
        await card(pg, "mail").locator(".bf button", has_text="Send to").click()
        rows, states = 0, set()
        for _ in range(80):
            await pg.wait_for_timeout(400)
            rows = max(rows, await card(pg, "round").locator("tbody tr").count())
            for t in await card(pg, "round").locator("td.s").all_inner_texts():
                states.add(t.strip().lower())
            if await card(pg, "cmp").locator("table.cmp tbody tr").count():
                break
        after = (await draft())["mail_approved"]
        c.is_(before is False and after is True,
              "sending is a button, and it writes the approval the server checks",
              f"{before} -> {after}")
        c.at_least(rows, 5, "the round shows a row per vendor while it runs")
        c.is_("quote read" in states,
              "each reply reaches 'quote read' as its document is parsed",
              str(sorted(states)))
        r = await pg.evaluate("fetch('/api/round').then(r => r.json())")
        c.eq(r.get("state"), "complete",
             "the round finishes, and says so to anyone who opens the page")
        c.is_("done" in (await card(pg, "mail").get_attribute("class")),
              "the mail card closes once it has gone")

        # ---- the table, in the conversation --------------------------------
        scheduled = len((await draft())["line_nos"])
        c.eq(await card(pg, "cmp").locator("table.cmp tbody tr").count(), scheduled,
             "the table covers exactly the lines the buyer scheduled")
        c.eq(await card(pg, "cmp").locator(".legend").count(), 1,
             "with the legend that says what a coloured cell means")
        c.at_least(await card(pg, "cmp").locator("td.s-unresolved").count(), 1,
                   "gaps are shown as gaps, never as zero")

        # ---- what it means, and what to do ---------------------------------
        summ = card(pg, "summary")
        c.at_least(await summ.locator(".ocard").count(), 2,
                   "the ways to award are cards you can compare")
        c.at_least(await summ.locator(".ocard .pick").count(), 2,
                   "and each one can be taken, not just read")
        c.at_least(await summ.locator(".sug").count(), 2,
                   "with what to do about it in words")
        c.is_("80%" in await summ.inner_text(),
              "including where the money actually is")

        # ---- round two: the mails that fill the gaps ------------------------
        gaps = card(pg, "gaps")
        c.at_least(await gaps.locator(".gap").count(), 2,
                   "every vendor with something missing gets an ask")
        c.is_("units at stake" in await gaps.inner_text(),
              "and the ask says what answering it is worth")
        await gaps.locator(".gap .rfoot button", has_text="Show the mail").first.click()
        await pg.wait_for_timeout(700)
        c.at_least(len(await gaps.locator(".mailbody-ro").first.inner_text()), 200,
                   "the follow-up is a real mail, composed from the gaps")

        unresolved_before = (await pg.evaluate(
            "fetch('/api/state').then(r => r.json())"))["counts"]["unresolved"]
        await gaps.locator(".gap .rfoot button", has_text="Send it").first.click()
        for _ in range(60):
            await pg.wait_for_timeout(500)
            if await card(pg, "moved").count():
                break
        c.eq(await card(pg, "moved").count(), 1,
             "a reply comes back and says what it changed")
        unresolved_after = (await pg.evaluate(
            "fetch('/api/state').then(r => r.json())"))["counts"]["unresolved"]
        c.is_(unresolved_after < unresolved_before,
              "and the whole pipeline re-runs on it — cells that were gaps resolve",
              f"{unresolved_before} -> {unresolved_after}")
        c.eq(await card(pg, "cmp").locator("table.cmp tbody tr").count(), scheduled,
             "the table above is the one that changed, not a second copy")

        # ---- evidence: every number opens its source -----------------------
        cells = card(pg, "cmp").locator("table.cmp tbody td.num")
        opened = 0
        for i in range(2, min(await cells.count(), 30)):
            await cells.nth(i).click()
            await pg.wait_for_timeout(400)
            if await pg.locator("#drawer.open").count():
                opened += 1
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(150)
            if opened >= 2:
                break
        c.at_least(opened, 2, "cells open their source document in the drawer")

        # ---- where the money is --------------------------------------------
        await summ.locator(".bf button", has_text="Where is the money").click()
        for _ in range(25):
            await pg.wait_for_timeout(400)
            if await card(pg, "spend").locator(".fig").count() >= 2:
                break
        c.eq(await card(pg, "spend").locator(".fig").count(), 2,
             "spend concentration and price spread both render")
        c.at_least(await card(pg, "spend").locator(".fig .bar").count(), 40,
                   "a bar per line in each")
        c.at_least(await card(pg, "spend").locator(".fig .bar.tail").count(), 1,
                   "the tail is de-emphasised rather than recoloured")
        await card(pg, "spend").locator(
            ".fig svg g rect[fill='transparent']").first.hover()
        await pg.wait_for_timeout(400)
        c.is_(not await pg.locator("#tip").is_hidden(), "every bar has a hover layer")
        c.is_("%" in await pg.locator("#tip").inner_text(),
              "and it names the line, the spend and the share")
        await card(pg, "spend").locator(".fig .foot button").first.click()
        await pg.wait_for_timeout(400)
        c.at_least(await card(pg, "spend").locator(".fig table.sheet tbody tr").count(),
                   20, "and a table view exists for anyone the chart does not serve")

        # ---- the memo ------------------------------------------------------
        await summ.locator(".ocard .pick").last.click()
        for _ in range(25):
            await pg.wait_for_timeout(400)
            if await card(pg, "memo").locator(".md").count():
                break
        c.at_least(len(await card(pg, "memo").inner_text()), 800,
                   "each option writes its own award memo")

        # ---- the trust layer: a human verdict is an input, not a comment ----
        if not await pg.locator("#chipReview").is_hidden():
            await pg.click("#chipReview")
            await pg.wait_for_timeout(1200)
            rev = card(pg, "reviews")
            # The queue is DECISIONS, not cells: twenty-nine of the latter,
            # three of the former. Its length is the known weakness of this
            # build, and grouping is the fix that does not work by hiding.
            c.at_least(await rev.locator(".rgroup").count(), 2,
                       "the review queue groups its cells by cause")
            in_groups = await pg.evaluate(
                "() => [...document.querySelectorAll('.rgroup .n')]"
                ".reduce((a, e) => a + parseInt(e.textContent), 0)")
            c.at_least(in_groups, 10, "every open cell sits inside a group")
            c.is_(await rev.locator(".rgroup .rcells").first.is_hidden(),
                  "the cells start folded behind the decision")
            await rev.locator(".rgroup .rfoot button",
                              has_text="Show the cells").first.click()
            await pg.wait_for_timeout(500)
            c.is_(not await rev.locator(".rgroup .rcells").first.is_hidden(),
                  "and open on request")
            cell = rev.locator(".rgroup .rcells .cell", has=pg.locator(
                "button:text-is('Correct…')")).first
            await cell.locator("button", has_text="Correct").click()
            await pg.wait_for_timeout(300)
            c.eq(await cell.locator(".fixrow").count(), 1,
                 "the correction box is inline, not a browser dialog")
            await cell.locator(".fixrow input").fill("10.28")
            await cell.locator(".fixrow button", has_text="Save").click()
            await pg.wait_for_timeout(1100)
            c.is_("corrected" in await cell.inner_text(),
                  "a correction is accepted and re-normalised",
                  (await cell.inner_text()).replace("\n", " / ")[-70:])

            open_before = int((await pg.locator("#chipReview").inner_text()).split()[0])
            g2 = rev.locator(".rgroup").nth(1)
            n2 = int((await g2.locator(".n").inner_text()).split()[0])
            await g2.locator(".rfoot button", has_text="Accept all").click()
            await pg.wait_for_timeout(1500)
            open_after = await pg.evaluate(
                "fetch('/api/reviews').then(r => r.json()).then(j => j.open)")
            c.eq(open_after, open_before - n2,
                 "accepting a cause clears exactly its cells")

        # ---- and it survives a reload --------------------------------------
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(2600)
        c.at_least(await card(pg, "cmp").locator("table.cmp tbody tr").count(), 20,
                   "a reload mid-tender lands on the table, not on an empty page")
        c.eq(await card(pg, "summary").count(), 1,
             "with what it means still under it")

        # ---- the door for a reviewer whose model call fails ----------------
        # /api/issue_default is demo insurance, and it is also the endpoint that
        # 500-ed on the live site for a week: the deploy runs EXTRACTOR=replay
        # with no recording committed, and the pipeline refused to replay a run
        # that was never made. Nothing else on this page calls it, so nothing
        # else catches that.
        httpx.post(f"{url}api/reset", timeout=10)
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(600)
        # Read the body before navigating away, or the aborted download is
        # reported as a failed request and blamed on the page.
        st = await pg.evaluate(
            "fetch('/api/issue_default', {method:'POST'})"
            ".then(async r => { await r.text(); return r.status; })")
        c.eq(st, 200, "the template RFx still issues in the deploy's own "
                      "extractor configuration")
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(2200)
        c.at_least(await card(pg, "cmp").locator("table.cmp tbody tr").count(), 20,
                   "and lands the reviewer on a real comparison")

        await b.close()

    c.is_(not problems, "no uncaught exception and no console error",
          "; ".join(problems[:3]))


def main() -> int:
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n  playwright is not installed. This check is optional:\n"
              "      pip install playwright && playwright install chromium\n")
        return 0

    port = _free_port()
    # Run the server the way the DEPLOY runs it. This harness first ran with
    # the local default (fixture) while production sets replay, and the gap hid
    # a 500 on /api/issue_default that took out the entire second half of the
    # product on the live site -- the pipeline refused to replay a run that was
    # never recorded, and every check here passed regardless. A check that runs
    # a configuration nobody ships is checking the wrong program.
    env = {**os.environ, "EXTRACTOR": os.getenv("EXTRACTOR", "replay")}
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import httpx
        for _ in range(40):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=2).status_code == 200:
                    break
            except Exception:                                 # noqa: BLE001
                pass
            time.sleep(0.5)
        else:
            print("\n  the server never came up.\n")
            return 1

        print("\n  UI SMOKE — the real page, a real browser\n")
        import asyncio
        c = Checks()
        asyncio.run(run(port, c))
        return c.report()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()


if __name__ == "__main__":
    sys.exit(main())
