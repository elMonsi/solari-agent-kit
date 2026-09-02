# Five Build Ideas — Solari as the AI-Agent Infrastructure Layer

Each idea targets a **specific, sourced problem** from `AI-RESEARCH.md` and uses a
Solari primitive that the research literature *itself* names as the mitigation.
Together they cover the three failure domains: **safety** (1, 2), **governance**
(3), and **operations/reliability** (4, 5).

> Honesty note on assumptions: microVM isolation, millisecond snapshot/fork +
> resume, persistent profiles/volumes, rrweb session recording/replay, stealth +
> proxy + captcha, port-preview URLs, and live VNC are all confirmed from
> getsolari.com / docs.getsolari.com. Anything I have **not** confirmed —
> notably per-VM **network-egress allowlisting** — is flagged inline as
> "verify in docs" rather than assumed.

---

## Idea 1 — Quarantine Browser: prompt-injection blast-radius containment

**Problem it solves.** Indirect prompt injection + the "lethal trifecta"
(untrusted content + private data + an egress channel in one context). Real
cases: EchoLeak (CVE-2025-32711), the Comet account-takeover chain, ChatGPT
Atlas omnibox injection. OpenAI/Anthropic now call injection *possibly
permanent*. The named architectural fix is a **trust boundary** (dual-LLM:
privileged model never touches raw untrusted content).

**The build.** A two-session agent pattern implementing dual-LLM on real infra:
- **Quarantined reader** — a Solari stealth browser in a *disposable* microVM,
  **no profile, no credentials, killed after the run**. It reads the untrusted
  page and returns only *structured, schema-validated* extractions (never raw
  text/HTML that could carry instructions).
- **Privileged actor** — a *separate* Solari session that attaches the real
  profile and acts, consuming only the sanitized structured object. It never
  sees the page.
- Every action is captured via **session recording** so you can prove the
  privileged step only ever saw sanitized input.

**Solari primitives.** Ephemeral microVM isolation (blast-radius containment),
profiles (privileged phase only), session recording (proof of the boundary).
*Verify in docs:* whether egress from the quarantined VM can be allowlisted for
defense-in-depth.

**Demo that lands.** Point it at a page containing a hidden "delete all files /
email my cookies" injection. Show the naive single-agent baseline obeying it,
then show the quarantine architecture ignoring it because the privileged actor
structurally never received the instruction.

---

## Idea 2 — Untrusted-Code Gateway: RCE containment for coding agents

**Problem it solves.** Coding agents run with developer privileges and
auto-execute untrusted config/code. Named CVEs: CurXecute (CVE-2025-54135),
mcp-remote RCE (CVE-2025-6514, CVSS 9.6), Claude Code init-time shell exec
(CVE-2025-59536). "Opening an untrusted project" is now itself the risk. The
Replit incident (prod DB wiped during a freeze) shows the operational cost. Fix
the research names: **sandboxed least-privilege execution, allowlists not
denylists, reversible/forkable runs.**

**The build.** A drop-in "safe exec" tool an agent calls instead of running code
on the host: every LLM-generated command, build, or untrusted repo clone is
routed into a fresh Solari **sandbox microVM**. Add:
- **Snapshot-before, roll-back-after** so a destructive command is reversible —
  fork the VM, run the risky op on the fork, keep it only if it verifies.
- **Per-command approval gate** for anything flagged destructive/network.
- Exit codes + recording returned as a tamper-evident execution log.

**Solari primitives.** Sandbox microVM isolation, snapshot/fork (reversibility),
fast spin-up (~90ms so gating each op is cheap). *Verify in docs:* egress
allowlisting and filesystem scoping.

**Demo that lands.** Clone a repo whose `postinstall` tries to read `~/.ssh` and
POST it out. Show it running harmlessly inside the disposable VM, the exfil
attempt visible in the recording, and the host untouched.

---

## Idea 3 — Glass Box: compliance-grade audit & replay for agent runs

**Problem it solves.** You can't reproduce an agent bug by re-running it
(inference is non-deterministic even at temp 0), and enterprises/regulators need
to know *what the agent actually did*. **EU AI Act Article 12** mandates
automatic event logging for high-risk systems (phasing in 2026–2027). OTel
GenAI conventions are still experimental; trace volume is breaking tooling
(ClickHouse acquired Langfuse, Jan 2026). Fix the research names:
**event-sourced capture + replay-from-logs, not re-execution.**

**The build.** A thin wrapper that turns any browser/desktop/sandbox agent run
into a portable, replayable audit artifact:
- Solari **session recording** (rrweb, DOM-level, greppable/diffable) is the
  action ledger; interleave it with a structured event log of every LLM
  decision, tool call, and approval.
- Ship a **replay viewer** that plays the run back deterministically from the
  log, and a **diff mode** that shows where two runs of the same task diverged
  (directly attacks the non-determinism/reproducibility gap).

**Solari primitives.** Session recording/replay (the whole idea rides on this
being first-class), VNC for desktop runs.

**Demo that lands.** Run the same task twice, show the two runs diverge, and
replay both from the log to pinpoint the divergent step — the thing you *cannot*
do by re-execution. Tie the output format to Article 12 logging requirements.

---

## Idea 4 — Freeze & Hand Off: durable pause/resume for human-in-the-loop

**Problem it solves.** The hard HITL problem isn't *asking* the human — it's
durably suspending a long run, persisting full state, and resuming without
re-running side effects, while not paying for an idle VM. LangGraph/Temporal
solve the *orchestration* checkpoint; nobody cheaply snapshots the *whole live
environment*. Also Problem 7: agents are billed while idle waiting on humans.
Replit shows what unsupervised destructive actions cost.

**The build.** An agent that, on hitting a risk gate (login wall, payment,
captcha it shouldn't auto-solve, destructive op):
1. **Snapshots its Solari VM** and parks it (scale-to-zero — no idle billing).
2. Hands a human a **live VNC / port-preview URL** to take over *inside the same
   environment* (finish the login, approve the purchase).
3. **Resumes from the exact snapshot** — same cookies, same page, same process
   state — in sub-second, continuing from where it stopped.

**Solari primitives.** Memory snapshot + sub-second resume ("freeze a machine
and fork it back later"), live VNC desktop for takeover, port-preview for
browser handoff, profiles/volumes for persisted state.

**Demo that lands.** Agent fills a checkout, stops at 2FA, snapshots and parks;
you get a VNC link, type the 2FA code by hand; agent resumes and completes the
order — with zero re-execution of prior steps and zero idle cost during the wait.

---

## Idea 5 — Best-of-N on Real State: a reliability harness against compounding error

**Problem it solves.** Success decays as p^N over long horizons (95%/step → 36%
at 20 steps); τ-bench shows pass^8 < 25%; Vending-Bench shows drift. You can't
prompt your way out of exponential decay. Fix the research names:
**checkpointing, bounded independently-verifiable steps, idempotent + rollback
tools, external structured state.** Everyone does best-of-N on *text*; nobody
does it on *live environment state* because forking a real environment is
expensive — except it isn't on Solari.

**The build.** A step executor that treats each risky action as a checkpointed,
verifiable unit:
- **Snapshot the VM** before a fragile step, **fork N copies**, run the step N
  ways in parallel microVMs, and keep only the fork whose result passes an
  explicit verifier (not just matches text — actually re-checks the resulting
  filesystem/DOM/state).
- On all-fail, **roll back to the snapshot** and retry with a different
  strategy. Persist verified state to a **volume** (external state, not chat
  history) so the transcript stays short (counters "context rot").

**Solari primitives.** Snapshot/fork + parallel microVMs (the enabler for
best-of-N on real state), volumes (external durable state), fast spin-up (makes
N forks per step economical).

**Demo that lands.** A 15-step web task that a single linear agent completes
~30% of the time; show the fork-verify-rollback harness pushing it to near-100%
by never letting a bad step propagate — the p^N curve visibly flattened.

---

## Why these five, as a system

| # | Domain | Sourced problem | Solari primitive as the fix |
| --- | --- | --- | --- |
| 1 | Safety | Prompt injection / lethal trifecta | Ephemeral isolation + profile separation + recording |
| 2 | Safety | Untrusted-code RCE | Sandbox microVM + snapshot rollback + gating |
| 3 | Governance | Non-reproducibility / audit (EU AI Act) | Session recording + replay/diff |
| 4 | Operations | HITL handoff + idle cost | Snapshot pause + VNC takeover + resume |
| 5 | Reliability | Compounding error (p^N) | Snapshot/fork + parallel VMs + volumes |

**The unifying insight (systemic view):** four of the five ride on one Solari
primitive the research repeatedly names as the missing substrate — a
**durable, snapshot-based freeze/fork/resume of a whole live environment.** That
single capability is the root fix for reversible safety (2), audit/replay (3),
human handoff + idle cost (4), and best-of-N reliability (5). Leading with a
build that showcases *snapshot/fork as the primitive* is the strongest possible
answer to this challenge, because it demonstrates you understand not just what
Solari does, but *why its architecture is the answer to the field's hardest
problem.*
