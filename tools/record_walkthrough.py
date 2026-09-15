"""
Record the walkthrough. No narration, no captions — a clean visual track.

The brief asks for a recorded walkthrough, and the part that is being marked is
the buyer's own commentary. So this does not try to be the commentary: it drives
the real product through the real flow at a pace somebody can talk over, and
prints the timestamp of every beat so the narration can be written against it.

Nothing here is staged. It is the same server the deploy runs, in the same
extractor configuration, driven through the same clicks a person would make —
which also makes it a second, slower smoke test: if a beat below cannot happen,
the product cannot do it.

What is NOT in the footage: the analyst's own turns. Those need a model API key,
this container has none, and putting one here to make a demo look complete is
the exact move this project argues against. Record those live against the
deployed instance, which has a key.

Run:  python -m tools.record_walkthrough            # ~7 minutes, writes an mp4
      python -m tools.record_walkthrough --fast     # same beats, no dwell time
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "walkthrough"
W, H = 1280, 800

# A pointer, because Playwright's recording does not draw one and a demo where
# buttons press themselves reads as a screenshot slideshow. It moves before it
# clicks, at a speed a viewer can follow.
CURSOR = r"""
(() => {
  if (window.__cur) return;
  const init = () => {
    const c = document.createElement('div');
    c.id = '__cursor';
    c.style.cssText = 'position:fixed;left:0;top:0;z-index:99999;width:24px;' +
      'height:24px;pointer-events:none;transform:translate(640px,400px);' +
      'transition:transform .5s cubic-bezier(.33,.06,.26,1);' +
      'filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24">' +
      '<path d="M5.5 2.5l13.2 7.6-5.8 1.3-2.7 5.6z" fill="#111418" ' +
      'stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    window.__cur = (x, y) => { c.style.transform = `translate(${x}px,${y}px)`; };
    window.__pulse = () => {
      const m = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/.exec(c.style.transform);
      if (!m) return;
      const r = document.createElement('div');
      r.style.cssText = 'position:fixed;z-index:99998;width:26px;height:26px;' +
        'margin:-13px 0 0 -13px;border-radius:50%;pointer-events:none;' +
        'border:2px solid rgba(23,65,107,.85);background:rgba(23,65,107,.18);' +
        `left:${+m[1] + 2}px;top:${+m[2] + 2}px;` +
        'animation:__pp .5s ease-out forwards';
      document.documentElement.appendChild(r);
      setTimeout(() => r.remove(), 520);
    };
    const st = document.createElement('style');
    st.textContent = '@keyframes __pp{0%{transform:scale(.4);opacity:1}' +
      '100%{transform:scale(1.7);opacity:0}}';
    document.documentElement.appendChild(st);
  };
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', init);
  else init();
})();
"""


def _free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Take:
    """The run, and the beat sheet it prints at the end."""

    def __init__(self, page, fast: bool) -> None:
        self.pg = page
        self.fast = fast
        self.t0 = time.time()
        self.beats: list[tuple[float, str]] = []

    # ---- pacing ----------------------------------------------------------
    def at(self) -> str:
        s = int(time.time() - self.t0)
        return f"{s // 60}:{s % 60:02d}"

    def beat(self, label: str) -> None:
        self.beats.append((time.time() - self.t0, label))
        print(f"  {self.at()}  {label}", flush=True)

    async def hold(self, seconds: float) -> None:
        """Dwell, so there is room to say something over it."""
        # A shade slower than real time. Somebody is going to talk over this,
        # and a beat that is gone before the sentence about it is finished is
        # a beat they have to edit around.
        await self.pg.wait_for_timeout(int((0.15 if self.fast else 1.15)
                                           * seconds * 1000))

    # ---- moving about ----------------------------------------------------
    async def point(self, loc) -> None:
        try:
            await loc.scroll_into_view_if_needed(timeout=4000)
        except Exception:                                     # noqa: BLE001
            return
        await self.pg.wait_for_timeout(250)
        box = await loc.bounding_box()
        if not box:
            return
        await self.pg.evaluate("([x, y]) => window.__cur && window.__cur(x, y)",
                               [box["x"] + box["width"] / 2,
                                box["y"] + box["height"] / 2])
        await self.pg.wait_for_timeout(520 if not self.fast else 120)

    async def click(self, loc, settle: float = 0.9) -> bool:
        await self.point(loc)
        try:
            await self.pg.evaluate("() => window.__pulse && window.__pulse()")
            await loc.click(timeout=8000)
        except Exception as e:                                # noqa: BLE001
            print(f"      (skipped a click: {type(e).__name__})", flush=True)
            return False
        await self.hold(settle)
        return True

    async def scroll_to(self, sel: str, block: str = "start",
                        settle: float = 1.0) -> None:
        await self.pg.evaluate(
            "([s, b]) => { const e = document.querySelector(s);"
            "              if (e) e.scrollIntoView({behavior:'smooth', block:b}); }",
            [sel, block])
        await self.pg.wait_for_timeout(700)
        await self.hold(settle)

    async def creep(self, sel: str, px: int, steps: int = 6) -> None:
        """Ease down a long block of text, the way a reader would."""
        for _ in range(steps):
            await self.pg.evaluate(
                "([s, d]) => { const e = document.querySelector(s);"
                "              if (e) e.scrollBy({top:d, behavior:'smooth'}); }",
                [sel, px // steps])
            await self.pg.wait_for_timeout(260 if not self.fast else 60)

    async def type_into(self, loc, text: str, delay: int = 32) -> None:
        await self.click(loc, settle=0.2)
        await loc.type(text, delay=0 if self.fast else delay)


async def run(port: int, fast: bool) -> list[tuple[float, str]]:
    from playwright.async_api import async_playwright

    url = f"http://127.0.0.1:{port}/"
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.webm"):
        f.unlink()

    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--force-color-profile=srgb"])
        ctx = await b.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=1,
            record_video_dir=str(OUT),
            record_video_size={"width": W, "height": H},
            color_scheme="light",
        )
        await ctx.add_init_script(CURSOR)
        pg = await ctx.new_page()
        t = Take(pg, fast)

        import httpx
        httpx.post(f"{url}api/reset", timeout=10)

        # ---- 1 · the empty page -----------------------------------------
        await pg.goto(url, wait_until="networkidle")
        await pg.wait_for_timeout(900)
        t.t0 = time.time()
        t.beat("the empty page — four steps, and the schedule is the first")
        await t.hold(5)
        await t.creep("#thread", 260, 5)
        await t.hold(3)

        items = pg.locator('[data-card="items"]')

        # ---- 2 · a quantity, and a line that is new this year ------------
        t.beat("a quantity moves — the item master is what we HAVE bought")
        qty = items.locator("table.pick tbody input.qty").nth(4)
        await t.click(qty, settle=0.3)
        await pg.keyboard.press("Control+a")
        await qty.type("140000", delay=0 if fast else 55)
        await pg.keyboard.press("Enter")
        await t.hold(3)

        t.beat("and a line the buyer added this year — no price history")
        await t.click(items.locator(".bf button", has_text="Add a line"))
        await t.type_into(items.locator(".addrow input.d"),
                          "Shelf-ready tray, 3-ply, 400x300x120 mm")
        await t.type_into(items.locator(".addrow input.q"), "50000")
        await t.hold(1.5)
        await t.click(items.locator(".addrow button", has_text="Add"))
        await t.hold(3)
        await t.click(items.locator(".bf button", has_text="Continue"))
        await t.hold(2)

        # ---- 3 · the vendors ---------------------------------------------
        t.beat("who is asked — this and the schedule cannot be fixed later")
        vend = pg.locator('[data-card="vendors"]')
        await t.hold(3)
        await t.click(vend.locator(".vcard").nth(3), settle=1.4)
        await t.click(vend.locator(".vcard").nth(3), settle=1.4)
        await t.click(vend.locator(".bf button", has_text="Continue"))
        await t.hold(2)

        # ---- 4 · the questionnaire, the gates, the terms ------------------
        qs = pg.locator('[data-card="questions"]')
        t.beat("nine questions, three of them disqualifying already")
        await t.hold(4)
        await t.click(qs.locator(".qrow").nth(1), settle=1.6)
        t.beat("drop the lead-time question and the fastest option cannot be built")
        await t.click(qs.locator(".qrow").nth(8), settle=2.4)
        await t.click(qs.locator(".qrow").nth(8), settle=1.4)
        t.beat("terms — what the move costs YOUR working capital, not what a "
               "vendor who has not replied would charge")
        await t.click(qs.locator(".terms button", has_text="30 days"), settle=3.5)
        await t.click(qs.locator(".terms button", has_text="45 days"), settle=3.0)
        await t.point(qs.locator("#due"))
        await t.hold(2)
        await t.click(qs.locator(".bf button", has_text="Continue"))
        await t.hold(2.5)

        # ---- 5 · the covering mail ---------------------------------------
        mail = pg.locator('[data-card="mail"]')
        t.beat("the covering mail, in full — composed from the draft, not written")
        await t.scroll_to('[data-card="mail"]', "start", 2.0)
        await t.creep('[data-card="mail"] textarea.mailbody', 520, 8)
        await t.hold(4)
        t.beat("and it is editable — your wording is what goes out")
        body = mail.locator("textarea.mailbody")
        await t.click(body, settle=0.2)
        await pg.keyboard.press("Control+End")
        await body.type("\n\nP.S. Quote against drawing revision C.",
                        delay=0 if fast else 38)
        await pg.keyboard.press("Tab")
        await t.hold(3)
        await t.scroll_to('[data-card="mail"] .bf', "end", 1.0)
        t.beat("send it — the server refuses without this button")
        await t.click(mail.locator(".bf button", has_text="Send to"), settle=0.5)

        # ---- 6 · the round ------------------------------------------------
        t.beat("the round — five formats, read one at a time")
        for _ in range(90):
            await pg.wait_for_timeout(400)
            if await pg.locator('[data-card="cmp"] table.cmp tbody tr').count():
                break
        await t.scroll_to('[data-card="round"]', "start", 4.0)

        # ---- 7 · the table -------------------------------------------------
        t.beat("every quote, landed, per buyer unit — in the conversation")
        await t.scroll_to('[data-card="cmp"]', "start", 4.0)
        await t.creep('[data-card="cmp"] .gridwrap', 420, 7)
        await t.hold(3)

        t.beat("any number opens the pixels it came from — the workbook")
        cell = pg.locator('[data-card="cmp"] table.cmp tbody tr').nth(2) \
                 .locator("td").nth(7)
        if await t.click(cell, settle=1.0):
            await t.hold(6)
            await t.creep("#dBody", 380, 6)
            await t.hold(3)
            await pg.keyboard.press("Escape")
            await t.hold(1.5)

        t.beat("and the photographed rate card, with its crop")
        cell = pg.locator('[data-card="cmp"] table.cmp tbody tr').nth(2) \
                 .locator("td").nth(4)
        if await t.click(cell, settle=1.0):
            await t.hold(7)
            await pg.keyboard.press("Escape")
            await t.hold(1.5)

        # ---- 8 · what it means ---------------------------------------------
        t.beat("what came back, and what to do about it")
        await t.scroll_to('[data-card="summary"]', "start", 4.0)
        await t.creep("#thread", 300, 5)
        await t.hold(4)
        await t.creep("#thread", 300, 5)
        await t.hold(4)
        await t.creep("#thread", 320, 5)
        await t.hold(5)

        # ---- 9 · round two --------------------------------------------------
        t.beat("a gap is not an answer — it is a mail, with what it is worth")
        await t.scroll_to('[data-card="gaps"]', "start", 4.0)
        gaps = pg.locator('[data-card="gaps"]')
        await t.click(gaps.locator(".gap .rfoot button",
                                   has_text="Show the mail").first, settle=1.0)
        await t.hold(7)
        t.beat("send it, and the whole pipeline runs again on the reply")
        await t.click(gaps.locator(".gap .rfoot button",
                                   has_text="Send it").first, settle=0.5)
        for _ in range(60):
            await pg.wait_for_timeout(500)
            if await pg.locator('[data-card="moved"]').count():
                break
        await t.scroll_to('[data-card="moved"]', "start", 6.0)
        t.beat("seven unresolved cells become one, and the table above changed")
        await t.scroll_to('[data-card="cmp"]', "start", 5.0)

        # ---- 10 · where the money is ----------------------------------------
        t.beat("where the money is, and where the competition is")
        await t.scroll_to('[data-card="summary"]', "start", 1.0)
        summ = pg.locator('[data-card="summary"]')
        await t.click(summ.locator(".bf button", has_text="Where is the money"),
                      settle=0.5)
        for _ in range(25):
            await pg.wait_for_timeout(400)
            if await pg.locator('[data-card="spend"] .fig').count() >= 2:
                break
        await t.scroll_to('[data-card="spend"]', "start", 4.0)
        bar = pg.locator('[data-card="spend"] .fig svg g rect[fill="transparent"]').nth(1)
        await t.point(bar)
        try:
            await bar.hover(timeout=5000)
        except Exception:                                     # noqa: BLE001
            pass
        await t.hold(4)
        await t.scroll_to('[data-card="spend"] .fig:nth-of-type(2)', "start", 4.0)
        await t.click(pg.locator('[data-card="spend"] .fig .foot button').last,
                      settle=3.0)

        # ---- 11 · the review queue ------------------------------------------
        if not await pg.locator("#chipReview").is_hidden():
            t.beat("twenty-nine cells, three decisions")
            await t.click(pg.locator("#chipReview"), settle=1.5)
            rev = pg.locator('[data-card="reviews"]')
            await t.scroll_to('[data-card="reviews"]', "start", 5.0)
            await t.click(rev.locator(".rgroup .rfoot button",
                                      has_text="Show the cells").first, settle=2.0)
            cellc = rev.locator(".rgroup .rcells .cell").first
            await t.click(cellc.locator("button", has_text="Correct"), settle=1.0)
            box = cellc.locator(".fixrow input")
            await t.click(box, settle=0.2)
            await pg.keyboard.press("Control+a")     # the box opens pre-selected
            await box.type("9.86", delay=0 if fast else 70)
            await t.hold(1.5)
            t.beat("a correction re-runs the eight steps and moves the number")
            await t.click(cellc.locator(".fixrow button", has_text="Save"), settle=2.5)
            await t.scroll_to('[data-card="cmp"]', "start", 4.0)
            await t.click(rev.locator(".rgroup .rfoot button",
                                      has_text="Accept all").nth(1), settle=3.0)

        # ---- 12 · the memo ---------------------------------------------------
        t.beat("the artifact that leaves the tool — on the card you picked")
        await t.scroll_to('[data-card="summary"]', "start", 1.0)
        await t.click(pg.locator('[data-card="summary"] .ocard .pick').last,
                      settle=1.0)
        for _ in range(25):
            await pg.wait_for_timeout(400)
            if await pg.locator('[data-card="memo"] .md').count():
                break
        await t.scroll_to('[data-card="memo"]', "start", 3.0)
        await t.creep("#thread", 900, 9)
        await t.hold(4)

        # ---- 13 · provenance --------------------------------------------------
        t.beat("and where the numbers came from, said out loud")
        await t.click(pg.locator("#chipAsm"), settle=1.5)
        await t.scroll_to('[data-card="asm"]', "start", 3.0)
        await t.creep("#thread", 500, 6)
        await t.hold(6)

        t.beat("end")
        await ctx.close()
        await b.close()
        return t.beats


def main() -> int:
    try:
        import playwright                                     # noqa: F401
    except ImportError:
        print("\n  playwright is not installed:\n"
              "      pip install playwright && playwright install chromium\n")
        return 1

    fast = "--fast" in sys.argv
    port = _free_port()
    # The deploy's own configuration, for the same reason the smoke test uses
    # it: a recording of a program nobody ships is a recording of the wrong
    # program.
    env = {**os.environ, "EXTRACTOR": os.getenv("EXTRACTOR", "replay")}
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import httpx
        for _ in range(40):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/healthz",
                             timeout=2).status_code == 200:
                    break
            except Exception:                                 # noqa: BLE001
                pass
            time.sleep(0.5)
        else:
            print("\n  the server never came up.\n")
            return 1

        print("\n  RECORDING — the real page, driven at talking pace\n")
        beats = asyncio.run(run(port, fast))
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()

    webm = sorted(OUT.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not webm:
        print("  no video was written.")
        return 1
    src = webm[-1]
    mp4 = OUT / "walkthrough.mp4"
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-c:v", "libx264", "-crf", "26",
             "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(mp4)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        mp4 = src

    sheet = OUT / "beats.md"
    lines = ["# Beat sheet", "",
             "Timestamps into `walkthrough.mp4`. The footage is silent on "
             "purpose — this is what is on screen when, so the narration can be "
             "written against it.", "",
             "| at | on screen |", "|---|---|"]
    for secs, label in beats:
        lines.append(f"| {int(secs) // 60}:{int(secs) % 60:02d} | {label} |")
    lines += ["", "The analyst's own turns are not in this take: they need a "
              "model API key, which this environment does not have. Record "
              "those against the deployed instance, which does."]
    sheet.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n  {mp4}   ({mp4.stat().st_size / 1e6:.1f} MB)")
    print(f"  {sheet}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
