"""check_recording.py — does session recording actually produce a replay on your plan?

Glass Box's decision-ledger half runs anywhere, but the DOM-level rrweb replay
depends on Solari **session recording** being available on your account. This is
a self-contained diagnostic that answers, unambiguously, "can I get a replay?":

  1. Launch a browser with recording=True.
  2. Drive REAL DOM activity (navigation, mouse, scroll, a click, back) so rrweb
     has mutations to capture — a 2s static page may record almost nothing.
  3. Release the session and wait for the async upload to flush.
  4. Poll download_replay() for up to ~3 minutes.

It prints exactly what happened, so the result is portable evidence. Run:

    export SOLARI_API_KEY=slr_live_...
    python check_recording.py

Timings here are deliberately generous (3x our in-demo defaults) to rule out
"too short / not flushed / polled too briefly" and isolate the real question:
is recording enabled on this plan?
"""
import asyncio
import inspect
import os
import time

from solari_browser import Solari
from solari_browser.errors import SolariError

# Generous (3x) timings so a negative result can't be blamed on impatience.
ACTIVITY_SETTLE_S = 3      # after initial load
POST_CLICK_S = 6           # after interacting
FLUSH_S = 9                # let rrweb batch flush before release
POLL_ATTEMPTS = 60         # x POLL_INTERVAL_S
POLL_INTERVAL_S = 3        # => up to 180s of polling


async def main() -> int:
    key = os.environ.get("SOLARI_API_KEY")
    if not key:
        print("Set SOLARI_API_KEY first.")
        return 2

    s = Solari(api_key=key)
    print("sessions methods :", [n for n in dir(s.sessions) if not n.startswith("_")])
    try:
        print("release_and_wait :", inspect.signature(s.sessions.release_and_wait))
    except (ValueError, TypeError):
        pass

    browser = await s.launch(recording=True)
    sid = browser.id
    print("session          :", sid)
    started = time.time()
    try:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await asyncio.sleep(ACTIVITY_SETTLE_S)
        # Generate DOM mutations so there is something to record.
        try:
            await page.mouse.move(120, 120)
            await page.mouse.move(320, 260)
            await page.evaluate("window.scrollBy(0, 200)")
            await page.locator("a").first.click()  # example.com's "More information..."
            await asyncio.sleep(POST_CLICK_S)
            await page.go_back()
        except Exception as e:  # noqa: BLE001 - activity is best-effort
            print("activity note    :", str(e)[:120])
        await asyncio.sleep(FLUSH_S)
    finally:
        await browser.close()
    print(f"session length   : ~{time.time() - started:.0f}s (recording flag was True)")

    # Force the post-release upload to flush before we poll, if supported.
    try:
        r = s.sessions.release_and_wait(sid)
        if asyncio.iscoroutine(r):
            r = await r
        print("release_and_wait :", str(r)[:120])
    except SolariError as e:
        print("release_and_wait :", f"status={getattr(e, 'status', None)} {str(e)[:100]}")
    except Exception as e:  # noqa: BLE001
        print("release_and_wait :", str(e)[:120])

    # Poll for the replay for up to POLL_ATTEMPTS * POLL_INTERVAL_S seconds.
    for attempt in range(1, POLL_ATTEMPTS + 1):
        await asyncio.sleep(POLL_INTERVAL_S)
        try:
            blob = await s.sessions.download_replay(sid)
            events = blob.decode(errors="replace").splitlines()
            print(f"\nREPLAY AVAILABLE after ~{attempt * POLL_INTERVAL_S}s: "
                  f"{len(blob)} bytes, {len(events)} rrweb events")
            print("first line:", events[0][:120] if events else "<empty>")
            await s.close()
            return 0
        except SolariError as e:
            st = getattr(e, "status", None)
            if attempt % 5 == 0 or st != 404:
                print(f"  {attempt * POLL_INTERVAL_S:>3}s: status={st} {str(e)[:70]}")
            if st != 404:
                break

    print(f"\nNO REPLAY after ~{POLL_ATTEMPTS * POLL_INTERVAL_S}s. "
          "recording=True was accepted but no replay was produced.\n"
          "With 3x-generous timings + real DOM activity ruled out, this indicates "
          "session recording is not enabled for this plan/account.")
    await s.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
