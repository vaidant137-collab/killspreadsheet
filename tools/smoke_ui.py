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

    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        pg.on("pageerror", lambda e: problems.append(f"uncaught: {e}"))
        # A 404 is reported by the console as "Failed to load resource" with no
        # URL attached, which is useless. Name the request.
        # Only same-origin failures are this page's problem. A blocked webfont
        # host (a sandbox, a corporate proxy) is a fact about the network, and
        # the stylesheet names a real fallback stack for exactly that case.
        pg.on("requestfailed", lambda r: problems.append(f"request failed: {r.url}")
              if r.url.startswith(url) else None)
        # 409 is this app saying "the RFx has not been issued", which is the
        # behaviour two checks below deliberately provoke. Every other 4xx/5xx
        # is a bug.
        pg.on("response", lambda r: problems.append(
            f"HTTP {r.status}: {r.url}  [after {len(c.rows)} checks]")
              if r.status >= 400 and r.status != 409 and r.url.startswith(url)
              else None)

        # ---- drafting half -------------------------------------------------
        import httpx
        httpx.post(f"{url}api/reset", timeout=10)
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(700)

        # Every element the script reaches for must exist. This is exactly
        # the shape of the bug that blanked the comparison grid: renderTable
        # kept writing to a header element a redesign had removed, threw, and
        # took enterComparison down with it. Cheap, and it covers the whole
        # file rather than only the paths this harness happens to walk.
        dangling = await pg.evaluate(r'''() => {
          const html = document.documentElement.outerHTML;
          const script = html.slice(html.indexOf("<scr" + "ipt"));
          const used = new Set();
          const res = [/\$\((?:"|')#([A-Za-z0-9_-]+)(?:"|')\)/g,
                       /getElementById\((?:"|')([A-Za-z0-9_-]+)(?:"|')\)/g];
          for (const re of res)
            for (const m of script.matchAll(re)) used.add(m[1]);
          return [...used].filter(id => !document.getElementById(id));
        }''')
        c.is_(not dangling, "every element the script reaches for exists",
              ", ".join(dangling))

        # Nothing the vendors have not sent may reach the drafting screen — and
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
                           "assumptions"])
            out[p] = (await fetch("/api/" + p)).status;
          return out;
        }""")
        c.is_(all(v == 409 for v in codes.values()),
              "endpoints that describe responses refuse before the RFx is issued",
              str(codes))

        c.at_least(await pg.locator("#suggest button").count(), 3,
                   "the empty chat offers openers")
        c.is_(not await pg.locator("#panelDraft").is_hidden(),
              "the draft panel is the pinned slot before quotes arrive")

        for tab, panel in (("items", "#panelItems"), ("vendors", "#panelVendors")):
            await pg.click(f'#tabs button[data-tab="{tab}"]')
            await pg.wait_for_timeout(350)
            c.is_(not await pg.locator(panel).is_hidden(), f"the {tab} tab opens")

        await pg.click('#tabs button[data-tab="items"]')
        await pg.wait_for_timeout(300)
        c.eq(await pg.locator("#panelItems select.catsel option").count(), 5,
             "five categories, four of them honestly empty")
        c.eq(await pg.locator("#panelItems table.pick tbody tr").count(), 30,
             "thirty lines in the item master")
        await pg.locator("#panelItems table.pick tbody tr").first.click()
        await pg.wait_for_timeout(500)
        d = (await pg.evaluate("fetch('/api/draft').then(r=>r.json())"))["draft"]
        c.eq(len(d["line_nos"]), 1, "a click writes to the draft, with no model call")
        await pg.locator("#panelItems .pfoot button",
                         has_text="Select all").click()
        await pg.wait_for_timeout(700)
        d = (await pg.evaluate("fetch('/api/draft').then(r=>r.json())"))["draft"]
        c.eq(len(d["line_nos"]), 30, "and so does scheduling the whole category")

        await pg.click('#tabs button[data-tab="vendors"]')
        await pg.wait_for_timeout(300)
        c.eq(await pg.locator("#panelVendors .vcard").count(), 5,
             "five approved vendors")
        await pg.locator("#panelVendors .pfoot button",
                         has_text="Invite all").click()
        await pg.wait_for_timeout(700)
        d = (await pg.evaluate("fetch('/api/draft').then(r => r.json())"))["draft"]
        c.eq(len(d["vendor_ids"]), 5, "inviting them all writes the vendor list")

        # ---- the co-pilot's turn, against a stubbed stream ------------------
        await pg.evaluate(STUB)
        await pg.fill("#q", "annual corrugated, back in two weeks")
        await pg.press("#q", "Enter")
        await pg.wait_for_timeout(1200)
        c.eq(await pg.locator("#chat .status", has_text="thinking").count(), 0,
             "the turn ends — it does not sit on 'thinking' for ever")
        c.at_least(await pg.locator(".block.choice .opt").count(), 2,
                   "the decision renders as options you click")
        c.is_("2 vendors move up" in await pg.locator(".block.choice").inner_text(),
              "each option carries its computed consequence")

        await pg.locator(".block.choice .opt", has_text="30 days").first.click()
        await pg.wait_for_timeout(900)
        d = (await pg.evaluate("fetch('/api/draft').then(r=>r.json())"))["draft"]
        c.eq(d["payment_terms_days"], 30,
             "picking terms writes the field that re-prices 139 cells")

        # ---- the mail, and sending it --------------------------------------
        # The buyer is about to write to five companies. What has to be in front
        # of them is the text that goes out and the list it goes to — not a note
        # saying a mail exists somewhere above.
        await pg.wait_for_timeout(900)
        mail = pg.locator("#chat .block.mail").last
        c.eq(await pg.locator("#chat .block.mail").count(), 1,
             "the covering mail appears once the RFx is complete")
        body = await mail.locator(".mailbody").inner_text()
        c.at_least(len(body), 400, "it is the whole mail, not a summary of it")
        c.is_("disqualif" in body.lower(),
              "and it tells the vendor which answers end their submission")
        c.eq(await mail.locator(".stub").count(), 1,
             "the card says on its face that the send is stubbed")
        c.is_(await mail.locator(".verify").count() == 1,
              "and asks the buyer to check the schedule and the vendor list")

        before = await pg.evaluate(
            "fetch('/api/draft').then(r => r.json()).then(j => j.draft.mail_approved)")
        await mail.locator(".rfoot button", has_text="Send to").click()

        # The round is the part a buyer lives in: mail out, replies landing one
        # at a time. Every row here is real work on a real document.
        rows, states = 0, set()
        for _ in range(60):
            await pg.wait_for_timeout(400)
            rows = max(rows, await pg.locator("#panelRound table.round tbody tr").count())
            for t in await pg.locator("#panelRound table.round td.s").all_inner_texts():
                states.add(t.strip().lower())
            if await pg.locator("#tableWrap table tbody tr").count():
                break
        after = await pg.evaluate(
            "fetch('/api/draft').then(r => r.json()).then(j => j.draft.mail_approved)")
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

        # ---- the comparison half -------------------------------------------
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(900)
        scheduled = len((await pg.evaluate(
            "fetch('/api/draft').then(r => r.json())"))["draft"]["line_nos"])
        c.eq(await pg.locator("#tableWrap table tbody tr").count(), scheduled,
             "the comparison covers exactly the lines the buyer scheduled")
        c.at_least(await pg.locator("#chat .options .card").count(), 3,
                   "the decision leads, before the table")

        await pg.click('#tabs button[data-tab="options"]')
        await pg.wait_for_timeout(1200)
        c.at_least(await pg.locator("#panelOptions .card").count(), 3,
                   "the options tab rebuilds them from the store")
        # Two questions a table sorted by line number cannot answer: which lines
        # are the money, and which lines anyone competed for.
        await pg.click('#tabs button[data-tab="spend"]')
        await pg.wait_for_timeout(2200)
        c.eq(await pg.locator("#panelSpend .fig").count(), 2,
             "spend concentration and price spread both render")
        c.at_least(await pg.locator("#panelSpend .fig .bar").count(), 40,
                   "a bar per line in each")
        c.at_least(await pg.locator("#panelSpend .fig .bar.tail").count(), 1,
                   "the tail is de-emphasised rather than recoloured")
        await pg.locator("#panelSpend .fig svg g rect[fill='transparent']").first.hover()
        await pg.wait_for_timeout(400)
        c.is_(not await pg.locator("#tip").is_hidden(),
              "every bar has a hover layer")
        c.is_("%" in await pg.locator("#tip").inner_text(),
              "and it names the line, the spend and the share")
        await pg.locator("#panelSpend .fig .foot button").first.click()
        await pg.wait_for_timeout(400)
        c.at_least(await pg.locator("#panelSpend .fig table.sheet tbody tr").count(), 20,
                   "and a table view exists for anyone the chart does not serve")

        await pg.click('#tabs button[data-tab="items"]')
        await pg.wait_for_timeout(400)
        c.eq(await pg.locator("#panelItems table.pick tbody tr").count(), 30,
             "the item master still loads AFTER the quotes arrive")
        await pg.click('#tabs button[data-tab="main"]')
        await pg.wait_for_timeout(400)

        # evidence: the claim that every number opens its source
        cells = pg.locator("#tableWrap table tbody td")
        opened = 0
        for i in range(3, min(await cells.count(), 30)):
            await cells.nth(i).click()
            await pg.wait_for_timeout(500)
            if await pg.locator("#drawer.open").count():
                opened += 1
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(200)
            if opened >= 2:
                break
        c.at_least(opened, 2, "cells open their source document in the drawer")

        # the trust layer: a human verdict is an input, not a comment
        if await pg.locator("#chipReview").count() and not await pg.locator("#chipReview").is_hidden():
            await pg.click("#chipReview")
            await pg.wait_for_timeout(1000)

            # The queue is DECISIONS, not cells: twenty-eight of the latter,
            # three of the former. The length of this queue is the known
            # weakness of the build, and grouping is the fix that does not work
            # by hiding errors.
            c.at_least(await pg.locator("#chat .rgroup").count(), 2,
                       "the review queue groups its cells by cause")
            in_groups = await pg.evaluate(
                "() => [...document.querySelectorAll('#chat .rgroup .n')]"
                ".reduce((a, e) => a + parseInt(e.textContent), 0)")
            c.at_least(in_groups, 10, "every open cell sits inside a group")
            c.is_(await pg.locator("#chat .rgroup .rcells").first.is_hidden(),
                  "the cells start folded behind the decision")
            await pg.locator("#chat .rgroup .rfoot button",
                             has_text="Show the cells").first.click()
            await pg.wait_for_timeout(500)
            c.is_(not await pg.locator("#chat .rgroup .rcells").first.is_hidden(),
                  "and open on request")
            # Scope to the review card itself. `#chat .card` also matches the
            # three option cards, and asserting against the wrong one passes or
            # fails for reasons that have nothing to do with corrections.
            card = pg.locator("#chat .rgroup .rcells .card", has=pg.locator(
                "button:text-is('Correct…')")).first
            await card.locator("button", has_text="Correct").click()
            await pg.wait_for_timeout(300)
            c.eq(await card.locator(".fixrow").count(), 1,
                 "the correction box is inline, not a browser dialog")
            await card.locator(".fixrow input").fill("10.28")
            await card.locator(".fixrow button", has_text="Save").click()
            await pg.wait_for_timeout(900)
            c.is_("corrected" in await card.inner_text(),
                  "a correction is accepted and re-normalised",
                  (await card.inner_text()).replace("\n", " / ")[-70:])

            # Accepting a whole cause is one judgement about one thing, and it
            # has to actually clear those cells rather than just grey a card.
            before = int((await pg.locator("#chipReview").inner_text()).split()[0])
            g2 = pg.locator("#chat .rgroup").nth(1)
            n2 = int((await g2.locator(".n").inner_text()).split()[0])
            await g2.locator(".rfoot button", has_text="Accept all").click()
            await pg.wait_for_timeout(1400)
            after = await pg.evaluate(
                "fetch('/api/reviews').then(r => r.json()).then(j => j.open)")
            c.eq(after, before - n2, "accepting a cause clears exactly its cells")

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
