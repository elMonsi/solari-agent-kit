# solari-agent-kit

**Five infrastructure patterns that fix the hardest problems in autonomous AI
agents — each built on [Solari](https://getsolari.com), the infrastructure layer
for AI agents.**

Built for the Solari hiring challenge. The thesis: the field's most-cited agent
failures — prompt injection, untrusted-code RCE, non-reproducibility,
human-handoff cost, and compounding unreliability — are not model problems. They
are *infrastructure* problems, and they share one root fix: a fast, isolated,
snapshot-able execution environment. That is exactly what Solari provides
(hardware-isolated microVMs, millisecond snapshot/fork + resume, persistent
profiles/volumes, session recording/replay, stealth browsers, live VNC).

## What we're building

Each pattern targets a specific, sourced problem and uses the Solari primitive
that the research literature itself names as the mitigation. Ranked by modeled
market impact (see the analysis docs):

| # | Pattern | Problem it solves | Solari primitive |
| --- | --- | --- | --- |
| 1 | **Best-of-N on Real State** | Compounding error over long horizons (p^N decay) | Snapshot/fork + parallel microVMs + volumes |
| 2 | **Untrusted-Code Gateway** | Coding-agent RCE from generated code / malicious MCP | Sandbox microVM + snapshot rollback + gating |
| 3 | **Quarantine Browser** | Indirect prompt injection / the "lethal trifecta" | Ephemeral isolation + profile separation + recording |
| 4 | **Freeze & Hand Off** | Human-in-the-loop handoff + idle-VM cost | Snapshot pause + VNC takeover + resume |
| 5 | **Glass Box** | Non-reproducibility + audit (EU AI Act Art. 12) | Session recording + replay/diff |

Each pattern ships as a small, self-contained, end-to-end runnable example
against the real Solari API — the same spirit as the Solari cookbook: one idea
each, no framework to read past, and the surprising bits documented right where
they bite.

## The unifying insight

Four of the five ride on one primitive the research repeatedly names as the
missing substrate: **durable snapshot / fork / resume of a whole live
environment.** Reversible safety, audit/replay, human handoff, and best-of-N
reliability are all the same capability viewed from different angles. This repo
demonstrates that capability as the answer to the field's hardest problems.

## Validation — all five run against the live Solari API ✅

Every pattern was executed end-to-end with a real `slr_live_` key (starter plan,
2026-09-02). Each pattern's own README has the full transcript and findings.

| # | Pattern | Result | Notes |
| --- | --- | --- | --- |
| 1 | Best-of-N on Real State | ✅ Core mechanic proven | Linear baseline fails at step 7; harness recovers via rollback+retry (steps 7, 10). Run with `DEMO_FORKS=2` on starter (2-concurrent cap). A transient control-channel drop (1005) hit the last step → add reconnect-retry. |
| 2 | Untrusted-Code Gateway | ✅ All 4 steps pass | Benign run, malicious-payload containment, destructive-op **restore-by-fork**, fail-closed deny gate. Fixed a bug: `revert()` 409s → rollback is fork-from-snapshot. |
| 3 | Quarantine Browser | ✅ Pass, no changes | Naive agent obeys all 5 injected actions; quarantine actor never receives the injection. |
| 4 | Freeze & Hand Off | ✅ Pass, state survives | `snapshot → pause (scale-to-zero) → human takeover → resume`; screenshot confirms document+cursor survived the freeze. Python `snapshot/pause/resume` all confirmed. |
| 5 | Glass Box | ✅ Audit half; ⚠️ replay plan-gated | Hash-chained decision ledger, `verify`, `show`, and same-task `diff` all work live. Live rrweb replay returned `404 "No replay available"` on starter → likely a plan-gated feature; re-verify on a plan with session recording. |

**Environment findings that apply repo-wide:**

- **Concurrency:** the starter plan allows **2 concurrent sessions** (sandboxes /
  browsers / desktops). Fan-out patterns must respect this.
- **Snapshots are large & chained** (~3.8 GB sandbox, ~5.5 GB desktop) and delete
  **leaf-first**; kill sandboxes before deleting an attached volume. Always purge
  after a run — see each README.
- **Rollback = fork-from-snapshot** (`create({ fromSnapshot })`), **not** in-place
  `revert()` (which returns 409 on a running VM).
- **Listing:** use `sandboxes.list()` (not `listAll()`, which returned `{}`).
  `sessions` (browser) has no `list()` — track sessions yourself.
- **Python behind an SSL-intercepting corporate proxy:** `pip install
  pip-system-certs` so `httpx` trusts the OS cert store (Node was unaffected).

## Repo layout

```
solari-agent-kit/
├── README.md
├── docs/                  # problem research, impact model, design notes
└── patterns/
    ├── 1-best-of-n/            (TypeScript)
    ├── 2-untrusted-code-gateway/  (TypeScript)
    ├── 3-quarantine-browser/  (TypeScript)
    ├── 4-freeze-and-handoff/  (Python)
    └── 5-glass-box/           (Python)
```

## Running

Each pattern is self-contained. You'll need a Solari API key
(`slr_live_...`, from [console.getsolari.com](https://console.getsolari.com)):

```bash
cd patterns/<name>
# npm install         (TypeScript)  or  pip install -r requirements.txt (Python)
export SOLARI_API_KEY=slr_live_...
# npm start / python main.py
```

## License

MIT
