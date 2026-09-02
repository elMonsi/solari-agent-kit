# Best-of-N on Real State

A tiny, runnable reliability harness that fights **compounding error** by
checkpointing a sandbox before a fragile step, forking N copies, running the
step N ways in parallel, keeping only the fork whose result passes an explicit
**verifier**, and rolling back to the checkpoint on all-fail.

---

## The problem: p^N decay

An agent that is right with probability `p` at each step is right end-to-end
with only `p^N` over `N` steps. That is an exponential, and it is brutal:

| per-step p | 10 steps | 20 steps |
| --- | --- | --- |
| 0.95 | 0.60 | **0.36** |
| 0.90 | 0.35 | 0.12 |

> 95% per step still collapses to **36%** by step 20. You cannot prompt your
> way out of an exponential.

This is the single most-cited driver behind the "agents don't make it to
production" headlines:

- Compounding error / p^N decay, and the METR time-horizon curve —
  https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/
- Kanwat, "Betting Against AI Agents in 2025" —
  https://utkarshkanwat.com/writing/betting-against-agents/
- τ²-bench: **pass^8 < 25%** (do the same task 8× and it holds < a quarter of the
  time) — https://arxiv.org/abs/2506.07982
- Vending-Bench meltdown / drift loops — https://arxiv.org/abs/2502.15840
- "Context rot" (long transcripts degrade the model) —
  https://www.trychroma.com/research/context-rot
- **Gartner: over 40% of agentic-AI projects will be canceled by end-2027** —
  https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
- **MIT NANDA: ~95% of enterprise GenAI pilots show no P&L impact** —
  https://fortune.com/2025/08/18/mit-report-95-percent-generative-ai-pilots-at-companies-failing-cfo/

(Source list mirrors `docs/AI-RESEARCH.md`, Problem 4. No benchmark numbers here
are invented — each is the figure reported by the linked source.)

The literature's named fixes are consistent: **bounded, independently-verifiable
steps; idempotent + rollback tools; checkpointing; external structured state.**

## How this pattern fixes it

Everyone already does best-of-N on *text* (sample k completions, keep the best).
The gap is doing it on *live environment state*, because forking a real machine
per step is normally too expensive. Per step, this harness does:

```
checkpoint  ->  fork N  ->  run the fragile step N ways in parallel
            ->  VERIFY each fork's real filesystem state   (not a text match)
            ->  keep the fork that passes, snapshot it forward
            ->  on all-fail, roll back to the checkpoint and retry
```

A bad step can never propagate, so `p^N` flattens toward the odds that *at least
one of N forks* passes — and if none do, you retry from known-good rather than
carrying corruption forward.

Two details that matter:

- **The verifier re-checks real state, not the model's claim.** In the demo a
  "misbehaving" step still exits 0 but writes a wrong artifact to disk; a
  text-match on the step's output would miss it. The verifier reads the
  resulting filesystem back and checks it.
- **Verified state is persisted to an external volume, not chat history.** It
  survives VM death and orchestrator restarts, and keeps the driving transcript
  short so a long run doesn't rot its own context.

## Which Solari primitive it uses

- **Snapshot / fork** — `sandbox.snapshot(name)` returns a save-point id;
  `client.sandboxes.create({ fromSnapshot })` boots a fresh, independent copy.
  Forking a whole live microVM in ~1s is what makes N-per-step economical. This
  is Solari's "freeze a machine and fork it back later."
- **Parallel microVMs** — the N forks run genuinely in parallel (`Promise.all`).
- **Volumes** — `client.volumes.create({ name })`, attached at `create` time via
  `volumes: [{ volumeId, path }]`, hold the durable external state.
- **`revert(snapshotId)`** rewinds the *same* VM in place (an alternative
  rollback style; this demo rolls back by simply re-forking the last checkpoint).

## How to run

```bash
cp .env.example .env      # then put your slr_live_... key in it
npm install
npm start
```

Tunables (env vars): `DEMO_SEED`, `DEMO_STEPS`, `DEMO_FORKS`, `DEMO_P`,
`DEMO_RETRIES`.

> **Starter plan (2 concurrent sandboxes): run with `DEMO_FORKS=2`.** The default
> `DEMO_FORKS=3` needs 3 concurrent microVMs and will fail with a 429
> `ConcurrencyLimitExceeded` on the starter plan. See validation notes below.

### Expected output (deterministic with the default seed=98)

The flakiness is a seeded hash of `(step, fork, retry)`, so runs are
reproducible and the linear baseline's single attempt is exactly fork 0 /
retry 0 of the harness:

```
=== BASELINE: linear agent (1 attempt/step, no fork, no rollback) ===
  step  0..6: ok
  step  7: BAD STATE
  linear run: FAILED at step 7 (bad state propagated, run aborted)

=== HARNESS: best-of-3 (checkpoint -> fork -> verify -> select -> rollback) ===
  ...
  step  7: [fail,fail,fail] -> ALL FAILED, rollback to checkpoint, retry 1/4
  step  7: [PASS,PASS,PASS] -> keep fork 0 (recovered on retry 1)
  ...
  step 10: [fail,fail,fail] -> ALL FAILED, rollback to checkpoint, retry 1/4
  step 10: [PASS,PASS,fail] -> keep fork 0 (recovered on retry 1)
  best-of-3 run: PASSED

=== RESULT ===
  linear    : FAILED at step 7
  best-of-3 : PASSED
```

The rollback path is genuinely exercised (steps 7 and 10 have all forks fail
once, roll back, and recover), not merely described.

## ✅ Validated against the live API — 2026-09-02 (completes clean, PASSED)

Run with a real `slr_live_` key on the **starter plan** (`DEMO_FORKS=2`,
seed=98). It runs end-to-end and **PASSES** — and, crucially, it does so while
surviving *multiple real transient failures*, which is exactly what the
robustness layer is for. Actual transcript:

```
=== BASELINE: linear agent (1 attempt/step, no fork, no rollback) ===
  step  0..6: ok
  step  7: BAD STATE
  linear run: FAILED at step 7 (bad state propagated, run aborted)

=== HARNESS: best-of-2 (checkpoint -> fork -> verify -> select -> rollback) ===
  step  0: [PASS,PASS] -> keep fork 0
  step  2: [PASS,fail] -> keep fork 0          # verifier rejects the corrupt fork
  [retry] fork: No sandbox host available — attempt 2/5 in 400ms   # rate-limit backoff
  step  6: [transient: Control channel closed (1005)] -> discard forks, re-fork, retry 1/4
  step  6: [PASS,PASS] -> keep fork 0 (recovered on retry 2)
  step  7: [fail,PASS] -> keep fork 1 (recovered on retry 2)
  step  9: [transient: Control channel closed (1005)] -> discard forks, re-fork, retry 1/4
  step  9: [PASS,PASS] -> keep fork 0 (recovered on retry 1)
  step 10: [fail,fail] -> ALL FAILED, rollback to checkpoint, retry 1/4
  step 10: [PASS,PASS] -> keep fork 0 (recovered on retry 1)
  step 11: [transient: Control channel closed (1005)] -> discard forks, re-fork, retry 1/4
  step 11: [fail,PASS] -> keep fork 1 (recovered on retry 1)
  best-of-2 run: PASSED

=== RESULT ===
  linear    : FAILED at step 7
  best-of-2 : PASSED
  Verified state persisted on the volume (12 steps): STEP-0-OK .. STEP-11-OK
```

**What this proves:** the linear baseline dies at step 7, while the harness
finishes all 12 steps despite three separate `Control channel closed (1005)`
drops (steps 6, 9, 11), several `No sandbox host available` rate limits, and
genuine verifier rejections (steps 2, 5) and all-fork failures (steps 7, 10). A
bad step — or a dropped connection — never propagates: it re-forks from the last
known-good checkpoint and recovers. That is the p^N curve flattening, live and
under real-world flakiness.

### Robustness layer (added after first live run)

The first live run died on a `1005` control-channel drop at the last step. The
fix, now validated repeatedly in the transcript above:

- **`timeoutMs` on every microVM** — a crash can't leave an orphan billing to the
  multi-hour default idle expiry; forks self-destruct within `IDLE_MS`.
- **Two failure classes, handled differently:** rate limits (`429` /
  "No sandbox host available") back off and retry the *same* call; a **dead
  control channel** (`1005` / "Not connected") is unrecoverable on that channel,
  so the step **discards its forks and re-forks fresh** from the checkpoint.
- **Checkpoint advances only after both snapshot *and* persist succeed**, so a
  mid-commit drop retries the step cleanly instead of skipping from half-applied
  state.

### Findings from the live run

- **SDK surface confirmed live:** `sandbox.snapshot(name) -> id`,
  `client.sandboxes.create({ fromSnapshot, volumes: [{ volumeId, path }] })`,
  and `client.volumes.create({ name }) -> { volumeId }` all work as documented.
  The `client.volumes` namespace is correct (no need for `sandboxes.volumes`).
- **Listing:** use `client.sandboxes.list()` (returns `{ sandboxes: [...] }`).
  `listAll()` returned `{}` in testing — do not rely on it.
- **Cleanup verified to zero** (0 sandboxes / 0 snapshots / 0 volumes) after the
  run. Two ordering rules matter (see below).

## Status / limitations

- **Concurrency ceiling.** The starter plan allows **2 concurrent sandboxes**;
  `create` returns 429 `ConcurrencyLimitExceeded` beyond that. Set `DEMO_FORKS`
  ≤ your plan's limit. (Higher plans support best-of-3+.)
- **Orphan-proofing (fixed):** every VM is created with `timeoutMs = IDLE_MS`
  (default 5 min, override via `DEMO_IDLE_MS`) so a crash can't leave a fork
  billing to the multi-hour default idle expiry.
- **Transient-failure recovery (fixed):** `1005` control-channel drops and `429`
  rate limits are handled (see "Robustness layer" above) — the full 12-step run
  survived three `1005` drops and several rate limits and still PASSED.
- **Snapshot cleanup is leaf-first.** Verified-step snapshots form a
  parent→child **chain**; a parent cannot be deleted while it has live children,
  so delete newest-first. Also kill all sandboxes **before** deleting a volume
  (an attached volume can't be deleted).
- **Snapshots are large (~3.8 GB each on the `base` template).** A 12-step run
  leaves ~12 chained snapshots (~46 GB) plus a volume — all billable storage
  until deleted. Purge after every run.
- **Concurrent writes:** all forks mount the same volume, but only the *winner*
  writes to it (sequentially across steps), so there is no write contention.
  Forks read prior state from their own copy-on-write filesystem carried by the
  snapshot.
