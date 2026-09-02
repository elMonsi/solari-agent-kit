# Untrusted-Code Gateway (TypeScript)

A drop-in **"safe exec"** an AI coding agent calls *instead of* running code on
the host. Every LLM-generated command, build, or untrusted repo clone is routed
into a disposable **Solari sandbox microVM** with least-privilege isolation, a
snapshot-before / roll-back-after option for destructive ops, and a per-command
approval gate for anything flagged destructive or network-touching.

## The problem

Coding agents run with **developer privileges** and auto-execute untrusted
config/code. "Opening an untrusted project" — or merely connecting to a
malicious MCP server — can trigger command execution *before any trust prompt
fires*. Real, recent CVEs:

- **CurXecute — CVE-2025-54135** (Cursor AI code editor)
  https://thehackernews.com/2025/08/cursor-ai-code-editor-fixed-flaw.html
- **mcp-remote RCE — CVE-2025-6514** (CVSS 9.6)
  https://thehackernews.com/2025/07/critical-mcp-remote-vulnerability.html
- **Claude Code init-time shell exec — CVE-2025-59536**
  https://thehackernews.com/2026/02/claude-code-flaws-allow-remote-code.html

And the operational cost when an agent runs destructive commands unsupervised:

- **Replit wiped a production database during a code freeze** ("catastrophic
  failure")
  https://fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/

The fix the research names (AI-RESEARCH.md, Problem 1b): **sandboxed
least-privilege execution, allowlists not denylists, and reversible / forkable
runs.**

## How the gateway fixes it

| Safeguard | What it does | Why (mapped to the problem) |
| --- | --- | --- |
| **Disposable microVM per run** | `safeExec()` spins a fresh Solari sandbox, runs the command, then `kill()`s it. Nothing it does can touch your machine or another tenant. | Even if malicious code runs *before* a trust prompt (CurXecute / mcp-remote / Claude Code CVEs), it runs in a throwaway box — least-privilege isolation. |
| **Approval gate (allowlist, fail-closed)** | Commands flagged `risky` must clear an explicit `approve()` decision; the default **denies**. | "Allowlists not denylists" + per-action confirmation for destructive/authenticated ops. You can't enumerate every dangerous command, so deny-by-default. |
| **Snapshot -> run -> rollback** | For a `risky` op, `safeExec()` calls `snapshot()` before running and `revert()`s the VM afterward, so a destructive command is fully reversible. | Directly prevents the Replit-style irreversible prod wipe: the destructive op happens, is observed, and leaves no lasting damage. |
| **Tamper-evident result** | Returns `{ exitCode, stdout, stderr, ran, rolledBackTo, ranIn }` so the agent sees exactly what happened and where. | Execution log the agent can inspect / audit. |

## Solari primitive used

**Sandbox microVM** (`SolariClient.sandboxes`): a headless Linux microVM that
boots from a memory snapshot in ~1s, isolated from your machine and other
tenants — purpose-built for running untrusted / LLM-generated code. Plus its
**snapshot / revert** capability ("freeze a machine and fork it back later") for
reversibility.

Methods used: `sandboxes.create({ template, timeoutMs, fromSnapshot? })`,
`sandbox.connect()`, `sandbox.commands.run(cmd, { args })` (**not**
shell-interpreted — argv in `args`, or run `sh -c` explicitly),
`sandbox.files.write/readText`, `sandbox.snapshot(name)`,
`sandbox.revert(snapshotId)`, `sandbox.kill()`.

## What the demo shows

1. A benign command running in a disposable VM.
2. A **malicious payload**: a script plants a *decoy* `~/.ssh/id_rsa` (a
   placeholder, never a real key) inside the VM, reads it, and tries to POST it
   to `attacker.example`. It runs **harmlessly** — the secret it reads is the
   decoy in the throwaway VM, the host's real `~/.ssh` is never in scope, and
   the entire exfil attempt is **visible in the returned log**.
3. **snapshot -> destructive `rm -rf` -> rollback**: a seeded file is deleted,
   then the VM is reverted to the pre-run snapshot, proving the destructive op
   was reversible.
4. The **approval gate DENY path**: with no approver, a risky command
   (`rm -rf /`) is blocked and never executes.

## How to run

```bash
cd patterns/2-untrusted-code-gateway
npm install
cp .env.example .env          # then edit .env
export SOLARI_API_KEY=slr_live_...   # https://console.getsolari.com
npm start
```

## Status / limitations

- **Not run against the live Solari API.** This example was written and
  type-reviewed but not executed end-to-end against a real key. Exact
  argument/return shapes may differ slightly from what's shown.
- **Snapshot / revert / `fromSnapshot`** (`sandbox.snapshot(name)`,
  `sandbox.revert(snapshotId)`, `sandboxes.create({ fromSnapshot })`) are
  confirmed from the docs at https://docs.getsolari.com/snapshots and
  https://docs.getsolari.com/sandboxes, but were **not verified against a live
  SDK build**. If your installed `@solarisdk/sdk` names these differently (e.g.
  `sandboxes.snapshot(id)` vs `sandbox.snapshot()`), adjust the two calls in
  `index.ts` marked around the snapshot/rollback flow. Treat them as the one
  spot to double-check.
- **`commands.run` stderr**: `stdout`/`exitCode` are confirmed; `stderr` is read
  defensively (`out.stderr ?? ""`) in case the field name differs.
- **Egress allowlisting / filesystem scoping** are *not* configured here.
  AI-RESEARCH.md (Problem 1b / Idea 2) flags per-VM network-egress allowlisting
  and filesystem scoping as **unconfirmed** in the Solari docs — the demo relies
  on VM disposability (kill after run) for containment, and the exfil attempt is
  allowed to fail naturally rather than being blocked at the network layer. If
  Solari exposes egress allowlisting, add it to `sandboxes.create()` for
  defense-in-depth.
- The `risky` flag is set by the caller in this demo. In production you'd wire a
  real classifier (destructive verbs, network tools, package post-install hooks)
  into the gate.
- **npmjs.com** returned HTTP 403 during verification, so the package version
  (`^0.1.2`) is matched to the cookbook examples rather than confirmed live.
