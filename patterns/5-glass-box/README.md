# Glass Box — compliance-grade audit & replay for agent runs (Python)

Turn an agent browser run into a **portable, replayable audit artifact**: a
DOM-level recording of what the *page* did, interleaved with an immutable,
hash-chained event log of what the *agent decided* — plus a tool to reconstruct
and **diff** runs from the logs instead of re-executing them.

Solari primitive: cloud-browser **session recording / replay**
(`solari.launch(recording=True)` + `solari.sessions.download_replay(id)`).

---

## The problem

Two facts that don't get along:

1. **Regulators need to know what the agent actually did.** The **EU AI Act,
   Article 12** mandates *automatic event logging* over a high-risk AI system's
   lifetime, with records that are traceable and appropriate to the risk
   (obligations phasing in 2026–2027).
   → https://artificialintelligenceact.eu/article/12/

2. **You cannot reproduce an agent run by re-running it.** LLM inference is
   **non-deterministic even at temperature 0** — floating-point/kernel
   scheduling and batch-variance mean identical inputs can yield different
   outputs. "Just run it again to see what happened" is not an audit strategy.
   → https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/

And the tooling that's supposed to help is still settling: OpenTelemetry's **GenAI
semantic conventions are explicitly experimental**, and trace volume is straining
the ecosystem (ClickHouse acquired Langfuse, Jan 2026).
→ https://opentelemetry.io/blog/2025/ai-agent-observability/

(Sources above are drawn from this repo's `docs/AI-RESEARCH.md`, Problem 5.)

## How event-sourced capture + replay/diff fixes it

The fix the literature names is **event-sourced capture + replay-from-logs, not
re-execution**: record every decision, tool call and approval as an immutable
record the instant it happens, and reconstruct the run from that ledger.

Glass Box keeps **two interleaved ledgers per run**:

| Ledger | Source | Answers |
| --- | --- | --- |
| DOM-level action ledger | Solari session recording (rrweb NDJSON) | what the *page* did |
| Decision ledger | this example's `ledger.py` (JSON-lines) | what the *agent* decided |

The decision ledger is **append-only and hash-chained** (each record's hash feeds
the next, blockchain-style). Edit or delete any record and every later hash fails
to verify — the tamper-resistance Article 12 asks for. Because the run *is* the
ordered list of immutable events, you replay it deterministically from the log —
no browser, no model, no network.

`replay.py diff` then runs the payload demo: take two runs of the **same task**
and show exactly where they diverged. That divergence is the reproducibility gap
made concrete — and the ledger is the only artifact that can show it, because
re-execution *is* the second, divergent run.

Since the "decision" step here stands in for a real (non-deterministic) LLM call,
`main.py --demo` will usually produce two runs that pick different actions — the
same way a temp-0 model would.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | Run the task with `recording=True`, emit the decision ledger, download the rrweb replay. `--demo` runs it twice and diffs. |
| `ledger.py` | Append-only, hash-chained JSON-lines event log + verifying reader. |
| `replay.py` | `verify` / `show` (replay-from-log) / `diff` — the reproducibility utility. |
| `requirements.txt` | `solari-browser>=0.1.3` |
| `.env.example` | `SOLARI_API_KEY=` (only needed for a live run) |

Each run writes `runs/<run_id>/events.jsonl` (decision ledger) and, on a live run,
`runs/<run_id>/replay.ndjson` (rrweb DOM ledger).

## How to run

```bash
cd patterns/5-glass-box
pip install -r requirements.txt
export SOLARI_API_KEY=slr_live_...        # https://console.getsolari.com

# The headline demo: same task twice, then diff the ledgers.
python main.py --demo

# One live run -> a full audit artifact under runs/<id>/
python main.py

# No key / no network? The ledger + diff still work end-to-end:
python main.py --demo --offline

# Inspect any artifact:
python replay.py verify runs/<id>/events.jsonl   # tamper check (exit 3 if broken)
python replay.py show   runs/<id>/events.jsonl   # replay the run from the log
python replay.py diff   runs/<A>/events.jsonl runs/<B>/events.jsonl
```

In `--offline` mode the Solari calls are skipped (recorded in the ledger as
skipped), so you can see the event-sourcing, tamper-check and diff without a key
or a live session. A live run adds the real rrweb replay.

## Status / limitations

- **Not run against the live Solari API.** The offline path (`--offline`,
  `replay.py verify/show/diff`) was executed and works; the live path was written
  against the recording cookbook example and the docs but not exercised.
- **Confirmed SDK surface** (docs.getsolari.com + the `browser-session-recording-py`
  cookbook): `Solari(api_key=...)`, `solari.launch(recording=True)`, `browser.id`,
  `browser.new_page()`, `page.goto()`, `page.locator(...).inner_text()`,
  `browser.close()`, `solari.close()`, `solari-browser>=0.1.3` (latest on PyPI,
  released 2026-09-01).
- **`TODO: verify` — `solari.sessions.download_replay(session_id)` (Python name).**
  The docs document only the **camelCase** `sessions.downloadReplay` (TypeScript);
  the snake_case Python name, the gzip **auto-decompress** behavior (don't
  `gzip.decompress()`), and the **async-upload / 404-then-poll** behavior all come
  from the Python cookbook example rather than the published API reference.
- **`TODO: verify` — `sessions.getReplayUrl` / `get_replay_url`.** The docs mention
  a `getReplayUrl(sessionId)` returning a shareable link; this example does not use
  it (it downloads the raw NDJSON instead). Python name unconfirmed.
- **The "decision" step is a stochastic stand-in for an LLM call**, not a real
  model. It exists to demonstrate the non-determinism/divergence honestly; swap it
  for your model call in production. Divergence in `--demo` is therefore
  probabilistic — re-run if two runs happen to match.
- **No figures are fabricated;** every citation above traces to `docs/AI-RESEARCH.md`.
