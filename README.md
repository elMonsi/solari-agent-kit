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

## Status

🚧 Early. Scaffolding and the first patterns are in progress. See each
`patterns/<name>/` directory for its own README and runnable example.

## Repo layout (planned)

```
solari-agent-kit/
├── README.md
├── docs/                  # problem research, impact model, design notes
└── patterns/
    ├── 1-best-of-n/
    ├── 2-untrusted-code-gateway/
    ├── 3-quarantine-browser/
    ├── 4-freeze-and-handoff/
    └── 5-glass-box/
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
