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
| **Snapshot -> run -> restore-by-fork** | For a `risky` op, `safeExec()` calls `snapshot()` before running and returns the snapshot id; to roll back you **fork** it into a fresh VM (`create({ fromSnapshot })`), so a destructive command is fully reversible. | Directly prevents the Replit-style irreversible prod wipe: the destructive op happens, is observed, and leaves no lasting damage. |
| **Tamper-evident result** | Returns `{ exitCode, stdout, stderr, ran, snapshotId, ranIn }` so the agent sees exactly what happened and where. | Execution log the agent can inspect / audit. |

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
`sandboxes.deleteSnapshot(id)`, `sandbox.kill()`. Rollback is
**fork-from-snapshot** (`create({ fromSnapshot })`), *not* in-place `revert()`
(see validation note below).

## What the demo shows

1. A benign command running in a disposable VM.
2. A **malicious payload**: a script plants a *decoy* `~/.ssh/id_rsa` (a
   placeholder, never a real key) inside the VM, reads it, and tries to POST it
   to `attacker.example`. It runs **harmlessly** — the secret it reads is the
   decoy in the throwaway VM, the host's real `~/.ssh` is never in scope, and
   the entire exfil attempt is **visible in the returned log**.
3. **snapshot -> destructive `rm -rf` -> restore-by-fork**: a seeded file is
   deleted (gone in the mutated VM), then the pre-wipe snapshot is forked into a
   fresh VM where the file is back — proving the destructive op was reversible.
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

## ✅ Validated against the live API — 2026-09-02

Run with a real `slr_live_` key on the starter plan. **All four steps pass.**
Actual transcript:

```
[1] Benign command in a disposable microVM:
    exit=0 stdout=5050 ranIn=solari-sandbox-microvm

[2] Malicious payload (fake secret exfil) — contained in the VM:
    [payload] read secret from VM: FAKE-PLACEHOLDER-PRIVATE-KEY-not-a-real-secret
    [payload] attempting exfil POST to attacker.example ...
    [payload] exfil FAILED (contained: no host creds, disposable VM)
    exit=0 (host ~/.ssh untouched; only the VM decoy was read)

[3] snapshot -> destructive op -> restore-by-fork (reversible run):
    seeded /tmp/important.txt
    [gate] approving risky: rm -rf /tmp/important.txt
    ran=true exit=0 snapshotId=snap_...
    in mutated VM, /tmp/important.txt = "<gone>"

[4] Approval gate DENY (fail-closed default):
    ran=false exit=126
    [gateway] BLOCKED by approval gate: rm -rf /

    restoring by forking the pre-wipe snapshot ...
    in forked VM, /tmp/important.txt = "critical production data"
    -> destructive op was fully reversible (restore-by-fork)
```

### Findings from the live run

- **Containment works:** the malicious payload reads only the in-VM decoy and its
  exfil POST fails; the host is never in scope.
- **`sandbox.revert(snapshotId)` is NOT supported for in-place rollback** — it
  returned `409 "Not revertable"` on a running VM. **The working rollback is
  fork-from-snapshot**: `client.sandboxes.create({ fromSnapshot })` into a fresh
  VM (this is also how pattern 1 rolls back). The code was updated accordingly;
  `safeExec` now returns `snapshotId` and the demo restores by forking it.
- **`commands.run` returns `stdout` and `exitCode`;** `stderr` was empty in
  testing and is read defensively.
- **Concurrency:** the demo uses ≤1 sandbox at a time, so it runs fine on the
  starter plan's 2-concurrent limit.
- **Cleanup verified to zero** — the demo deletes its own pre-exec snapshot after
  restoring; account showed 0 sandboxes / 0 snapshots / 0 volumes afterward.

## Status / limitations
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
- **`@solarisdk/sdk@^0.1.2` installs and runs** against the live API (confirmed);
  the earlier npm-registry 403 during authoring was a fetch issue, not a version
  problem.
