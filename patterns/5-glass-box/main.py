"""Glass Box — turn an agent browser run into a portable, replayable audit artifact.

WHY THIS PATTERN EXISTS
-----------------------
Two facts that don't get along:

  1. Regulators want to know *what the agent actually did*. EU AI Act Article 12
     mandates automatic, tamper-resistant EVENT LOGGING over a high-risk system's
     lifetime (phasing in 2026-2027). See https://artificialintelligenceact.eu/article/12/
  2. You cannot reproduce an agent run by re-executing it. LLM inference is
     non-deterministic even at temperature 0 (batch-invariance / kernel
     scheduling — https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/).
     Re-running the "same" task gives you a *different* run, not the old one.

So "just run it again to see what happened" is not an audit strategy. The fix the
literature names is EVENT-SOURCED CAPTURE + REPLAY-FROM-LOGS: record every decision,
tool call and approval as an immutable record the moment it happens, and reconstruct
the run from that ledger instead of re-executing. (OpenTelemetry's GenAI semantic
conventions are still *experimental* — https://opentelemetry.io/blog/2025/ai-agent-observability/ —
so this example ships a small, portable JSON-lines schema rather than depending on them.)

Glass Box interleaves TWO ledgers for one run:

  * The DOM-level ledger  -> Solari session recording (rrweb NDJSON). What the *page* did.
  * The decision ledger   -> this file's EventLog.       What the *agent* decided.

Together they answer "what happened", and `replay.py` answers "where did two runs
of the same task diverge" — the thing you cannot get by re-execution.

RUN MODES
  python main.py                 # one live run  (needs SOLARI_API_KEY)
  python main.py --offline       # one run, no live browser (ledger only, for demoing)
  python main.py --demo          # run the SAME task twice, then diff the two ledgers
  python main.py --demo --offline

Solari primitive used: cloud-browser SESSION RECORDING / REPLAY
(`solari.launch(recording=True)` + `solari.sessions.download_replay(id)`).
"""

import argparse
import asyncio
import os
import random
import sys
import time
from pathlib import Path

# replay.py holds the ledger reader + diff/replay utilities; main.py reuses them
# so "--demo" can produce two runs and diff them in one command.
from ledger import EventLog, load_log
import replay

OUT_DIR = Path(__file__).parent / "runs"

# The logical task we audit. Deliberately tiny — the point is the audit artifact,
# not the browsing. "example.com" so the example is runnable and dependency-free.
TASK = "Open example.com, read its heading, decide the next action, and record everything."


def decide(page_heading: str) -> dict:
    """Stand-in for a real LLM planning call.

    In production this is a model call ("given this page, what do I do next?").
    We keep it stochastic ON PURPOSE: it is the honest analogue of the temp-0
    non-determinism cited above. Two runs of the identical task can pick different
    strategies / confidences — which is exactly the divergence `replay.py diff`
    surfaces. A real LLM would vary here even with fixed inputs and temperature 0;
    we do NOT seed the RNG so each run mirrors that.
    """
    strategies = [
        "click:more-information-link",
        "extract:page-title",
        "summarize:visible-text",
        "stop:task-complete",
    ]
    choice = random.choice(strategies)
    confidence = round(random.uniform(0.55, 0.99), 3)
    return {
        "observed_heading": page_heading,
        "chosen_action": choice,
        "confidence": confidence,
    }


async def run_task(run_id: str, offline: bool = False) -> Path:
    """Execute the task once and emit a complete audit artifact under runs/<run_id>/.

    Returns the path to the run's event ledger (events.jsonl).
    """
    run_dir = OUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = EventLog(run_dir / "events.jsonl", run_id=run_id)

    # Every step below is recorded the MOMENT it happens. Article 12 wants the log
    # written as events occur over the lifecycle, not reconstructed after the fact.
    log.emit("run_start", inputs={"task": TASK, "offline": offline})

    api_key = os.environ.get("SOLARI_API_KEY")
    live = bool(api_key) and not offline

    session_id = None
    heading = "Example Domain"  # fallback used in offline mode

    if live:
        # Import lazily so --offline works with no SDK installed / no network.
        from solari_browser import Solari
        from solari_browser.errors import SolariError

        solari = Solari(api_key=api_key)

        # recording=True is OPT-IN PER SESSION. A session launched without it records
        # nothing and its replay endpoint 404s forever — there is no account switch.
        browser = await solari.launch(recording=True)
        session_id = browser.id
        log.emit("browser_launch", inputs={"recording": True}, outcome={"session_id": session_id})
        try:
            page = await browser.new_page()
            await page.goto("https://example.com")
            log.emit("tool_call", inputs={"tool": "goto", "url": "https://example.com"},
                     outcome={"ok": True})

            heading = await page.locator("h1").inner_text()
            log.emit("extract", inputs={"selector": "h1"}, outcome={"heading": heading})

            # Give rrweb a moment to flush the events it batched before we release.
            await asyncio.sleep(2)
        finally:
            # browser.close() also releases the billed session — always in finally.
            await browser.close()
    else:
        # Offline: we don't touch Solari, but we still produce the decision ledger
        # so the audit artifact + diff are fully demonstrable without a live key.
        log.emit("browser_launch", inputs={"recording": True},
                 outcome={"session_id": None, "note": "offline: no live session"})
        log.emit("tool_call", inputs={"tool": "goto", "url": "https://example.com"},
                 outcome={"ok": True, "note": "offline (not executed)"})
        log.emit("extract", inputs={"selector": "h1"}, outcome={"heading": heading})

    # --- the non-deterministic decision (the reproducibility gap in miniature) ---
    t0 = time.perf_counter()
    decision = decide(heading)
    decision["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    log.emit("decision", inputs={"prompt": "next action?"}, outcome=decision)

    # A human/rule approval gate. Article 12 specifically wants approvals logged.
    approved = decision["chosen_action"] != "stop:task-complete"
    log.emit("approval", inputs={"proposed": decision["chosen_action"]},
             outcome={"approved": approved, "policy": "auto-approve non-terminal actions"})

    # --- download the DOM-level ledger (rrweb NDJSON) and store it beside events ---
    if live:
        from solari_browser.errors import SolariError

        replay_ok = False
        # Upload is ASYNC after the session is released, so the first polls 404 even
        # on a perfectly good recording. Retry ~30s before concluding there's none.
        for attempt in range(1, 11):
            await asyncio.sleep(3)
            try:
                blob = await solari.sessions.download_replay(session_id)
            except SolariError as err:
                if getattr(err, "status", None) == 404:
                    continue
                raise
            # Stored gzipped, but the HTTP client honours Content-Encoding and hands
            # back decompressed bytes — this is already plain NDJSON. Do NOT gunzip.
            (run_dir / "replay.ndjson").write_bytes(blob)
            rrweb_events = blob.decode().splitlines()
            log.emit("replay_download", outcome={"bytes": len(blob),
                                                 "rrweb_events": len(rrweb_events),
                                                 "attempts": attempt})
            replay_ok = True
            break
        if not replay_ok:
            log.emit("replay_download", outcome={"error": "no replay after ~30s"})
        await solari.close()
    else:
        log.emit("replay_download",
                 outcome={"note": "offline: no rrweb replay (would come from Solari)"})

    log.emit("run_end", outcome={"final_action": decision["chosen_action"]})
    return log.path


async def _demo(offline: bool) -> None:
    """Headline demo: run the SAME task twice, then diff the two decision ledgers.

    This is the payload of the whole pattern — you cannot get this by re-execution,
    because re-execution IS the second (divergent) run.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    a = await run_task(f"{stamp}-A", offline=offline)
    b = await run_task(f"{stamp}-B", offline=offline)
    print(f"\nRun A ledger: {a}")
    print(f"Run B ledger: {b}\n")
    print("=" * 70)
    print("DIFF  (same task, two runs - where did they diverge?)")
    print("=" * 70)
    diverged = replay.diff(load_log(a), load_log(b))
    if not diverged:
        print("\nThe two runs happened to match this time. Non-determinism is "
              "probabilistic — run --demo again to see them diverge.")


async def _single(offline: bool) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = await run_task(stamp, offline=offline)
    print(f"\nAudit artifact written: {path.parent}")
    print("Inspect / verify / replay it with:")
    print(f"  python replay.py verify {path}")
    print(f"  python replay.py show   {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Glass Box — audit & replay for agent runs.")
    ap.add_argument("--demo", action="store_true",
                    help="run the task twice and diff the two ledgers")
    ap.add_argument("--offline", action="store_true",
                    help="produce the ledger without a live Solari session")
    args = ap.parse_args()

    if not args.offline and not os.environ.get("SOLARI_API_KEY"):
        print("No SOLARI_API_KEY set — falling back to --offline "
              "(ledger only, no live rrweb replay).\n", file=sys.stderr)
        args.offline = True

    coro = _demo(args.offline) if args.demo else _single(args.offline)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
