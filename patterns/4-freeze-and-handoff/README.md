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

During the human-takeover pause, open the printed `streamUrl` in a VNC viewer
(see note below — it's a `wss://` WebSocket stream, not a plain browser link),
then press ENTER in the console to resume. To run non-interactively, pipe a
newline: `echo "" | python main.py`.

## ✅ Validated against the live API — 2026-09-02

Run with a real `slr_live_` key on the starter plan. **Works end-to-end.** The
`FreezeHandoff` wrapper resolved to the *real* Python methods — no guessing
needed. Actual transcript:

```
opened mousepad, pid 510
  !! RISK GATE HIT: 2FA code required to authorize the purchase
  [FreezeHandoff] snapshot via desktop.snapshot('at-2fa-gate') -> snap_dl4ffxsyalrs
  [FreezeHandoff] parked via desktop.pause() — VM scaled to zero
  >> HUMAN TAKEOVER  ... Press ENTER once the human step is complete...
  [FreezeHandoff] resumed via desktop.resume(...) — state intact
screenshot: screenshot-after-resume.png (73816 bytes)
```

**State survived the freeze — verified from the screenshot.** After
`pause()` → `resume()`, the mousepad still showed the pre-freeze form line
(`... 2FA code:`) with the post-resume text (`status: 2FA cleared by human,
order CONFIRMED by agent`) appended right after it. Same document, same cursor
position — no re-execution of the earlier keystrokes.

### Findings from the live run

- **Python method names are all confirmed** on the `Desktop` object:
  `snapshot(name) -> id`, `pause()`, `resume()` all exist and work (also
  `revert`, `reconnect`, `preview_url`). The `FreezeHandoff` probe found each on
  its first candidate. (You can simplify it to direct calls now, or keep it as a
  portable shim.)
- **`pause`/`resume` work on desktops** with the expected semantics (parked, then
  resumed with state intact) — the earlier open question is resolved.
- **`streamUrl` is a `wss://` WebSocket VNC stream** (`wss://api.getsolari.com/stream/<id>`),
  not an `https` page — open it with a VNC-over-WebSocket viewer (e.g. noVNC),
  not directly in a browser address bar.
- **TLS behind a corporate proxy:** on a machine whose network does SSL
  interception with a private root CA, Python's `httpx`/`certifi` bundle rejects
  the chain (`CERTIFICATE_VERIFY_FAILED: self-signed certificate`). Fix without
  code changes: `pip install pip-system-certs` (bridges Python to the OS trust
  store). The Node patterns weren't affected. Env-specific, not a code issue.
- **Cleanup:** `client.destroy(sessionId)` runs in `finally` and removed the
  desktop; the demo **keeps** its `at-2fa-gate` snapshot (delete it afterward —
  desktop snapshots appear under `sandboxes.listSnapshots()` /
  `deleteSnapshot()`). Account verified back to 0 after cleanup. Note: desktop
  snapshots are large (~5.5 GB here).

## Status / limitations

- **The human wait is simulated** with `input()`/piped newline. In production the
  human's answer re-attaches to a durable run id (LangGraph/Temporal style) so
  the process can exit entirely while the VM stays parked.
- **Resume-latency figures** from the site (sub-second/"0.78ms") were not
  measured here, so none is quoted as fact.
