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

The rollback path is genuinely exercised (steps 7 and 10 have all three forks
fail once, roll back, and recover), not merely described.

## Status / limitations

- **Not yet run against a live Solari API.** The code is written to the
  documented SDK surface but has not been executed with a real `slr_live_` key.
  The console transcript above is derived from the demo's deterministic
  flakiness function (validated in isolation), not from a live run.
- **SDK method names were confirmed from docs, read via an automated fetcher,
  not from a live SDK.** Confirmed against `docs.getsolari.com/snapshots`,
  `/volumes`, and `/sdk/typescript/sandboxes` (Sep 2026):
  `sandbox.snapshot(name?) -> string`, `sandbox.revert(id)`,
  `create({ fromSnapshot })`, `create({ volumes: [{ volumeId, path }] })`,
  `volumes.create({ name }) -> { volumeId }`. These are the pieces the brief
  flagged as previously UNCONFIRMED; they are now documented, but treat them as
  doc-confirmed, not run-confirmed.
- **One namespace ambiguity to verify:** the TS SDK overview shows top-level
  `client.volumes.create(...)` (used here), while the volumes page shows
  `sandboxes.volumes.create(...)`. If `client.volumes` errors, switch to
  `client.sandboxes.volumes`. Flagged inline with `TODO: verify` in `index.ts`.
- **"Fork" is not a method** — it is `create({ fromSnapshot })`, wrapped in a
  local `fork()` helper so there is one place to change if the surface differs.
- **Cost/quota:** each successful step spins up N microVMs (plus retries). With
  defaults that is up to a few dozen short-lived VMs per full run. Fast boot is
  what makes this affordable, but it is not free — mind your quota.
- **Concurrent writes:** all forks mount the same volume, but only the *winner*
  writes to it (sequentially across steps), so there is no write contention.
  Forks read prior state from their own copy-on-write filesystem carried by the
  snapshot.
