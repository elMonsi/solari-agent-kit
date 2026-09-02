"""Freeze & Hand Off — durable pause/resume for human-in-the-loop.

A computer-use agent drives a real Solari desktop until it hits a *risk gate* it
must not cross on its own — a login wall, a 2FA prompt, a payment, a destructive
op. At that point, instead of either (a) blindly clicking through (the Replit
prod-DB-wipe failure mode) or (b) holding a live VM open and *billing you while
it waits on a human* (the "inference paradox" idle-cost failure mode), it:

    1. SNAPSHOTS its desktop VM and PARKS it (pause → scale-to-zero, no idle bill).
    2. Hands a human the live VNC `streamUrl` to take over *inside the same
       environment* and finish the sensitive step by hand.
    3. RESUMES from the exact snapshot and continues — same cookies, same window,
       same process state, with **no re-execution** of the prior steps.

WHY this matters (sourced in AI-RESEARCH.md, Problems 6 & 7):

  - The hard part of human-in-the-loop is NOT asking the human. It is durably
    suspending a long run, persisting *full* state, and resuming without
    re-running side effects. LangGraph `interrupt()`/`resume` and Temporal's
    durable agent harness solve this for the *orchestration graph* — but they
    checkpoint your control flow, not the live desktop/browser the agent was
    driving. Solari snapshots the *whole live environment*, so "resume" means the
    cursor is still blinking in the same text box.
        LangGraph interrupt/resume:
          https://www.langchain.com/blog/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt
        Temporal durable agent harness:
          https://temporal.io/blog/temporal-agent-harness-durable-agent-infrastructure

  - Unsupervised agents crossing destructive gates is not hypothetical: Replit's
    coding agent wiped a production database *during a change freeze* and called
    it a "catastrophic failure." A hard freeze-for-human gate on
    destructive/authenticated ops is exactly the guardrail that was missing.
        https://fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/

  - Paying for a VM to sit idle while it waits on a human is the "inference
    paradox": inference is getting cheaper per token, yet cost *per workflow* is
    projected to rise ~5x through 2028 — pain is idle time, not unit compute.
    Parking the VM (scale-to-zero) instead of holding it open is the fix the
    research names.
        https://www.computerworld.com/article/4210786/ai-inference-is-getting-cheaper-but-your-agents-are-getting-more-expensive.html

Solari's site pitches exactly this primitive: "freeze a machine and fork it back
later," machines that "start from a memory snapshot, so they are live in
milliseconds rather than booting."

--------------------------------------------------------------------------------
STATUS / VERIFICATION (read before trusting the freeze calls)
--------------------------------------------------------------------------------
This example has NOT been run against the live Solari API.

CONFIRMED from the cookbook + docs.getsolari.com:
  - Desktop lifecycle: DesktopClient(api_key, base_url), client.create(
    template, resolution, timeout_ms), desktop.connect(), desktop.health().ready,
    desktop.open(app), desktop.mouse.click(x, y, humanize), desktop.keyboard.type(
    text), desktop.screenshot(format), desktop.sessionId, desktop.streamUrl,
    teardown desktop.close() then client.destroy(sessionId).
  - The freeze/fork/resume *concepts* and their TypeScript method names:
    `sbx.snapshot(name)`, `sbx.revert(id)`, `create({ fromSnapshot })`,
    `sbx.pause()`, `sbx.resume()`; for desktops `desktop.pause()` and
    `desktops.connect(id)` which "resumes if paused". (docs.getsolari.com
    /snapshots and /desktops — examples shown are TypeScript only.)

UNCONFIRMED:
  - The exact *Python* method names for snapshot/pause/resume on `solari-desktop`.
    The docs only show TypeScript. Every snapshot/pause/resume call below is
    therefore routed through the `FreezeHandoff` wrapper, which tries the likely
    Python spellings (snake_case first) and FAILS LOUDLY listing what it tried,
    rather than silently inventing a method. Search this file for
    `TODO: verify against Solari SDK`.
"""

import asyncio
import os
import pathlib

from solari_desktop import DesktopClient

BASE_URL = "https://api.getsolari.com"


# =============================================================================
# FreezeHandoff — thin wrapper over the UNCONFIRMED Python snapshot/pause/resume
# surface. See STATUS block above. TODO: verify against Solari SDK.
# =============================================================================
#
# The TypeScript names are confirmed; the Python spellings are not. To stay
# honest we do NOT hard-code a single guessed name. Each operation probes a small
# ordered list of plausible attribute names on the live object and calls the
# first that exists. If none exist, it raises with the full list it tried so the
# gap is obvious at runtime instead of hidden behind a fake method.
class FreezeHandoff:
    @staticmethod
    async def _call_first(obj, candidates, *args, **kwargs):
        """Call the first attribute in `candidates` that exists on `obj`."""
        for name in candidates:
            fn = getattr(obj, name, None)
            if callable(fn):
                result = fn(*args, **kwargs)
                # SDK is async; await if we got a coroutine back.
                if asyncio.iscoroutine(result):
                    result = await result
                return name, result
        raise NotImplementedError(
            "Could not find any of "
            f"{candidates!r} on {type(obj).__name__}. "
            "TODO: verify against Solari SDK — the freeze/resume Python method "
            "names are unconfirmed (docs show TypeScript only)."
        )

    @staticmethod
    async def snapshot(desktop, name):
        # TS-confirmed: `sbx.snapshot(name)` returns a snapshot id.
        # TODO: verify against Solari SDK (Python name unconfirmed).
        used, snap_id = await FreezeHandoff._call_first(
            desktop, ["snapshot", "create_snapshot", "createSnapshot"], name
        )
        print(f"  [FreezeHandoff] snapshot via desktop.{used}({name!r}) -> {snap_id}")
        return snap_id

    @staticmethod
    async def park(desktop):
        # TS-confirmed: `desktop.pause()` — parks the machine, saves state, and
        # per the docs "won't be shut down for being idle" (scale-to-zero: no
        # idle billing during the human wait).
        # TODO: verify against Solari SDK (Python name unconfirmed).
        used, _ = await FreezeHandoff._call_first(desktop, ["pause", "park", "stop"])
        print(f"  [FreezeHandoff] parked via desktop.{used}() — VM scaled to zero")

    @staticmethod
    async def resume(client, desktop, session_id):
        # TS-confirmed: `desktops.connect(id)` re-attaches and "resumes if
        # paused"; `sbx.resume()` wakes a paused machine. We try the object-level
        # resume first, then the client-level reconnect-by-id.
        # TODO: verify against Solari SDK (Python names unconfirmed).
        for target, candidates, args in (
            (desktop, ["resume", "unpause"], ()),
            (client, ["connect", "resume", "reconnect"], (session_id,)),
        ):
            try:
                used, _ = await FreezeHandoff._call_first(target, candidates, *args)
                tname = "desktop" if target is desktop else "client"
                print(f"  [FreezeHandoff] resumed via {tname}.{used}(...) — state intact")
                return
            except NotImplementedError:
                continue
        raise NotImplementedError(
            "No resume/reconnect method found on desktop or client. "
            "TODO: verify against Solari SDK."
        )


async def needs_human(reason: str) -> None:
    """Simulated risk gate. In a real agent this is where a classifier flags a
    login wall / 2FA / payment / destructive op and refuses to proceed alone."""
    print(f"\n  !! RISK GATE HIT: {reason}")
    print("     Agent will NOT cross this on its own (see Replit prod-DB-wipe).")


async def wait_for_human(stream_url: str) -> None:
    """Hand the live environment to a human and block until they signal done.

    Here we print the VNC `streamUrl` and wait on stdin. In production this is a
    durable run id the human's answer re-attaches to (LangGraph/Temporal style),
    so the process can exit entirely while the VM stays parked — zero idle cost.
    """
    print("\n  >> HUMAN TAKEOVER")
    print(f"     Open this live VNC stream and finish the step by hand:\n       {stream_url}")
    print("     (Same cookies / same window / same process — you are *inside* the agent's VM.)")
    # Non-blocking-ish: run the blocking input() off the event loop.
    await asyncio.to_thread(input, "\n     Press ENTER once the human step is complete... ")


async def main() -> None:
    async with DesktopClient(
        api_key=os.environ["SOLARI_API_KEY"],
        base_url=BASE_URL,
    ) as client:
        desktop = await client.create(
            template="default",
            resolution="1280x720",
            # Rolling idle window. Note: we don't rely on this for the human wait
            # — we PARK the VM instead, so the wait costs nothing regardless.
            timeout_ms=10 * 60_000,
        )
        session_id = desktop.sessionId
        print("session:", session_id)
        print("watch  :", desktop.streamUrl)

        try:
            await desktop.connect()

            # Wait for X11 before driving the GUI.
            for _ in range(30):
                health = await desktop.health()
                if getattr(health, "ready", False):
                    break
                await asyncio.sleep(1)

            # ---------------------------------------------------------------
            # PHASE 1 — agent drives the desktop up to the risk gate.
            # We use mousepad as a stand-in "form": the agent types the part it
            # is allowed to (e.g. shipping details), then stops at the 2FA field.
            # ---------------------------------------------------------------
            pid = await desktop.open("mousepad")
            print("opened mousepad, pid", pid)
            await asyncio.sleep(4)

            # Click INSIDE the editor before typing (screen-centre misses it).
            await desktop.mouse.click(320, 300, humanize=True)
            await desktop.keyboard.type(
                "CHECKOUT FORM (filled by agent)\n"
                "  name: Ada Lovelace\n"
                "  ship: 1 Analytical Engine Way\n"
                "  2FA code: "  # <- agent stops exactly here
            )
            await asyncio.sleep(2)

            # ---------------------------------------------------------------
            # PHASE 2 — hit the gate, snapshot, park (scale-to-zero), hand off.
            # ---------------------------------------------------------------
            await needs_human("2FA code required to authorize the purchase")
            snap_id = await FreezeHandoff.snapshot(desktop, "at-2fa-gate")
            await FreezeHandoff.park(desktop)
            # From here until resume, the VM is parked: no idle billing while the
            # human works. The process could even exit and re-attach later by id.
            await wait_for_human(desktop.streamUrl)

            # ---------------------------------------------------------------
            # PHASE 3 — resume from the exact snapshot and continue.
            # No re-typing of the form: the prior keystrokes are still on screen.
            # ---------------------------------------------------------------
            await FreezeHandoff.resume(client, desktop, session_id)
            # Re-establish the local control channel after the park/resume cycle.
            await desktop.connect()
            for _ in range(30):
                health = await desktop.health()
                if getattr(health, "ready", False):
                    break
                await asyncio.sleep(1)

            # Continue right where we left off — append the confirmation the
            # agent is allowed to do post-2FA. If state persisted correctly, the
            # screenshot below shows the WHOLE form, not just this line.
            await desktop.keyboard.type("\n  status: 2FA cleared by human, order CONFIRMED by agent\n")
            await asyncio.sleep(2)

            shot = await desktop.screenshot(format="png")
            out = pathlib.Path("screenshot-after-resume.png")
            out.write_bytes(shot)
            print(f"\nscreenshot: {out} ({len(shot)} bytes)")
            print("If the form above the 2FA line is still present, state survived the freeze.")
            print(f"(snapshot kept: {snap_id})")
        finally:
            # close() drops only the local channel; destroy() ends the session.
            await desktop.close()
            await client.destroy(session_id)


if __name__ == "__main__":
    asyncio.run(main())
