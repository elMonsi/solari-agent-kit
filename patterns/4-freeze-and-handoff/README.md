# Freeze & Hand Off — durable pause/resume for human-in-the-loop (Python)

An agent drives a real Solari desktop until it hits a **risk gate** it must not
cross alone — a login wall, 2FA, a payment, a destructive op. Instead of clicking
through blindly *or* holding a live VM open while it waits on a human, it:

1. **Snapshots** its desktop VM and **parks** it (`pause` → scale-to-zero, no idle bill).
2. Hands a human the live VNC `streamUrl` to **take over inside the same environment** and finish the sensitive step by hand.
3. **Resumes from the exact snapshot** and continues — same cookies, same window, same process state, with **no re-execution** of prior steps.

## The problem (sourced)

The hard part of human-in-the-loop is not *asking* the human — it is durably
suspending a long run, persisting full state, and resuming **without re-running
side effects**, while not paying for an idle VM in the meantime. Three concrete
pressures from `docs/AI-RESEARCH.md`:

- **Unsupervised destructive actions are catastrophic.** Replit's coding agent
  wiped a **production database during a change freeze** and called it a
  "catastrophic failure." A hard freeze-for-human gate on destructive/authenticated
  ops is exactly the guardrail that was missing. (Problem 6) —
  https://fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/

- **Idle waiting is the real cost — the "inference paradox."** Inference gets
  cheaper per token, yet cost *per workflow* is projected to rise **~5x through
  2028**; the pain is idle time and context reprocessing, not unit compute. An
  agent billed while it blocks on a human is the anti-pattern. (Problem 7) —
  https://www.computerworld.com/article/4210786/ai-inference-is-getting-cheaper-but-your-agents-are-getting-more-expensive.html

- **Existing durable-interrupt tools checkpoint the graph, not the environment.**
  LangGraph `interrupt()`/`resume` and Temporal's durable agent harness durably
  suspend and resume the *orchestration control flow* — but they do not snapshot
  the live desktop/browser the agent was driving. (Problem 6)
  - LangGraph interrupt/resume — https://www.langchain.com/blog/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt
  - Temporal durable agent harness — https://temporal.io/blog/temporal-agent-harness-durable-agent-infrastructure

## How freeze / handoff / resume fixes it

Solari snapshots the **whole live environment**, so "resume" means the cursor is
still blinking in the same text box, the login is still half-filled, the process
is still running.

- **Snapshot at the gate** → an exact save point of the entire VM.
- **Park (pause)** → the VM scales to zero; a paused machine "won't be shut down
  for being idle," so the human wait costs nothing. The process can even exit and
  re-attach later by session id (LangGraph/Temporal durable-run-id style).
- **VNC takeover** → the human opens `streamUrl` and completes the sensitive step
  *inside the agent's own environment* (no divergent second context).
- **Resume** → reconnect by id; the machine wakes from the snapshot and the agent
  continues, with zero re-execution of the earlier steps.

Solari's own pitch for this: "freeze a machine and fork it back later"; machines
"start from a memory snapshot, so they are live in milliseconds rather than booting."

## Solari primitives used

| Primitive | Role here |
| --- | --- |
| Desktop microVM + live VNC (`streamUrl`) | The environment the agent drives and the human takes over |
| Memory snapshot (`snapshot`) | Exact save point at the risk gate |
| Pause / park | Scale-to-zero during the human wait — no idle billing |
| Resume / reconnect-by-id | Wake from snapshot and continue with no re-execution |
| Desktop control (`mouse`, `keyboard`, `screenshot`, `open`) | Drive the GUI and prove state persisted |

## Demo flow (`main.py`)

1. Create desktop, connect, wait for X11 (`health().ready`).
2. Agent opens mousepad and types a "checkout form," stopping exactly at the
   `2FA code:` field.
3. Risk gate hit → **snapshot** (`at-2fa-gate`) → **park** the VM → print the VNC
   `streamUrl` and wait for the human (press ENTER to simulate the human typing
   the 2FA code by hand in the stream).
4. **Resume**, reconnect, and the agent appends the post-2FA confirmation.
5. Screenshot `screenshot-after-resume.png` shows the **entire** form (the lines
   typed before the freeze are still there) — proof state survived the freeze.

## How to run

```bash
cd patterns/4-freeze-and-handoff
pip install -r requirements.txt
cp .env.example .env        # then edit, or just export the var below
export SOLARI_API_KEY=slr_live_...   # https://console.getsolari.com
python main.py
```

During the human-takeover pause, open the printed `streamUrl` in any VNC viewer
to watch/act live, then press ENTER in the console to resume.

## Status / limitations

**This example has NOT been run against the live Solari API.** It is written to
match the confirmed cookbook style and the documented API surface.

**Confirmed** (cookbook `desktop-computer-use-py` + docs.getsolari.com):
`DesktopClient(api_key, base_url)`, `client.create(template, resolution,
timeout_ms)`, `desktop.connect()`, `desktop.health().ready`, `desktop.open(app)`,
`desktop.mouse.click(x, y, humanize=...)`, `desktop.keyboard.type(text)`,
`desktop.screenshot(format=...)`, `desktop.sessionId`, `desktop.streamUrl`,
teardown `desktop.close()` then `client.destroy(sessionId)`.

**Confirmed concepts, TypeScript method names only** (docs.getsolari.com
`/snapshots` and `/desktops`): `snapshot(name)` returns a snapshot id;
`revert(id)`; `create({ fromSnapshot })`; `pause()` (parked machines "won't be
shut down for being idle"); `resume()`; and `desktops.connect(id)` which
"resumes if paused." All examples on those pages are TypeScript.

**UNCONFIRMED — needs verification before this runs for real:**

- The exact **Python** method names for snapshot / pause / resume on
  `solari-desktop`. The docs show TypeScript only, and the PyPI page for
  `solari-desktop` would not load (Cloudflare "client challenge") to confirm the
  Python surface.
- Because of that, `main.py` routes every freeze/resume call through the
  `FreezeHandoff` wrapper, which probes the likely Python spellings
  (`snapshot`/`pause`/`resume`, plus `desktops.connect(id)` to re-attach) and
  **fails loudly listing what it tried** rather than inventing a method. Search
  for `TODO: verify against Solari SDK`.
- Whether `pause`/scale-to-zero is available on **desktops** specifically (vs.
  headless sandboxes) with identical semantics.
- Resume-latency figures: the site references sub-second/millisecond resume but
  no exact per-call figure (e.g. "0.78ms") was confirmable in the docs, so none
  is quoted as fact here.
