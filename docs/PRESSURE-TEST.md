# Pressure-Test: Quantifying & Ranking the Five Ideas

Goal: decide which idea is *most impactful*, not by taste but by a transparent,
repeatable model. Every score has a cited justification (see `AI-RESEARCH.md`).

> **Honesty about the numbers.** The dollar/percent "anchors" below are *modeled
> estimates tied to real cited figures*, not measured results for these specific
> builds. Cited source numbers (CVSS scores, p^N math, Gartner/MIT/EU figures)
> are real; the extrapolations to a build's impact are labeled as models with a
> confidence tag. I flag every assumption rather than assume.

---

## The scoring model

Four dimensions, each scored **1–5**, combined by weight. Weights reflect the
question asked ("which is most impactful"), so **prevalence** and **how
completely Solari actually solves it** dominate; **spend-readiness** (a
regulatory or market forcing function) is the multiplier that turns a real
problem into real budget.

| Dimension | Weight | What a 5 means |
| --- | --- | --- |
| **Prevalence** — what share of agent deployments hit this | 0.25 | ~Every production agent encounters it |
| **Severity** — loss per incident / magnitude of the pain | 0.20 | Catastrophic (breach, project death, RCE) |
| **Solari Solve Fit** — how completely Solari's *confirmed* primitives fix it | 0.30 | Solari's core primitive *is* the textbook fix |
| **Spend-readiness (tailwind)** — regulatory/market force driving budget now | 0.25 | Hard mandate or #1 cited spend driver |

`Composite = 0.25·Prev + 0.20·Sev + 0.30·Fit + 0.25·Tailwind`

Fit is weighted highest on purpose: a problem Solari only *partially* addresses
is a weaker pitch than one its signature primitive nails, even if the problem is
huge.

---

## Scores (with cited justification)

### Idea 5 — Best-of-N on Real State (reliability / compounding error)
| Dim | Score | Why |
| --- | --- | --- |
| Prevalence | 5 | Universal: *every* multi-step agent. The #1 cited reason agent projects fail. |
| Severity | 5 | Existential — kills the whole deployment, not one run. |
| Fit | 4 | Snapshot/fork enables best-of-N on *live state* (Solari's edge); but needs app-level verifiers + N× token cost on gated steps. |
| Tailwind | 5 | Biggest market $ signal (Gartner 40% cancel; MIT 95% no P&L). |
| **Composite** | **4.70** | |

**Quantified anchor.** p^N is the killer: a 20-step task at 95%/step succeeds
only **36%** of the time. Wrapping the ~5 most fragile steps in best-of-3
fork-verify raises effective per-step reliability to 1−0.05³ ≈ **99.99%**,
lifting end-to-end success from **~36% → ~99%** (a **~2.7× completion-rate
gain**). *Model confidence: medium-high — the p^N math is exact; the assumption
is that a per-step verifier exists and forks are independent.* TAM anchor: this
is the exact failure behind Gartner's projected **>40% agentic-project
cancellation by 2027** and MIT's **95% of pilots with no P&L impact.**

---

### Idea 2 — Untrusted-Code Gateway (coding-agent RCE)
| Dim | Score | Why |
| --- | --- | --- |
| Prevalence | 4 | Every coding/MCP agent — huge, but a subset of all agents. mcp-remote CVE hit **437k+ downloads**. |
| Severity | 5 | RCE / full host compromise / prod-DB wipe — the highest per-incident severity. |
| Fit | 5 | A disposable microVM sandbox is the *textbook* fix — exactly what Solari sandboxes are for. |
| Tailwind | 4 | CVE flood (multiple CVSS 9.4–9.6) + enterprise security budgets. |
| **Composite** | **4.50** | |

**Quantified anchor.** Solving it means containing incidents whose severity is
**CVSS 8.6–9.6** (CurXecute, mcp-remote, Claude Code CVEs). "Saves Y" = one
prevented RCE breach ≈ **IBM's avg breach cost ~$4.4M**, plus the Replit-style
prod-DB-wipe class of loss. *Model confidence: high on severity (cited CVSS),
lower on frequency-per-org.* Prevalence anchor: essentially **100% of agents
that run generated code or connect to third-party MCP servers** are exposed
today.

---

### Idea 1 — Quarantine Browser (prompt injection / lethal trifecta)
| Dim | Score | Why |
| --- | --- | --- |
| Prevalence | 5 | ~Every browsing agent with credentials. **OWASP LLM01 — the #1 LLM risk.** |
| Severity | 5 | Account takeover, zero-click data exfiltration (EchoLeak, CometJacking). |
| Fit | 3 | Isolation + profile-separation contains blast radius, but the true fix is app-level dual-LLM architecture; Solari doesn't natively stop the model obeying, and per-VM egress allowlisting is **unconfirmed**. |
| Tailwind | 4 | Hot (OpenAI/Anthropic call it "possibly permanent"), but no single hard mandate. |
| **Composite** | **4.15** | |

**Quantified anchor.** Even Anthropic's own mitigations leave **11.2% autonomous
attack success** on Claude for Chrome. A dual-session quarantine architecture
*structurally* removes the instruction path to the privileged actor, targeting
the residual toward **~0%** for authenticated actions. *Model confidence: medium
— depends on the extraction schema being tight; a leaky schema re-opens the
channel.* Prevalence anchor: **#1 on the OWASP LLM Top 10**, i.e. the single
most-cited class of agent vulnerability.

---

### Idea 4 — Freeze & Hand Off (HITL + idle cost)
| Dim | Score | Why |
| --- | --- | --- |
| Prevalence | 4 | Broad: every long-running agent needs handoff; every agent is billed while idle. |
| Severity | 3 | Idle cost is continuous but individually moderate; handoff failure is recoverable. |
| Fit | 5 | Millisecond snapshot + resume is Solari's *signature* primitive — direct, near-complete. |
| Tailwind | 4 | Cost pressure: "inference paradox" — cost-per-workflow projected **~5× through 2028.** |
| **Composite** | **4.10** | |

**Quantified anchor.** Agents sit idle a large fraction of wall-clock waiting on
LLM latency and human approvals while a VM keeps billing. Snapshot-park +
scale-to-zero eliminates that window: on handoff-heavy workflows this is a
**modeled ~40–60% environment-cost reduction** (idle-share dependent). *Model
confidence: low-medium — the idle fraction varies wildly by workload; needs a
measured baseline to firm up.* This is the cleanest literal "**solving X saves
$Y**" story, but the per-unit magnitude is smaller than the project-death and
breach classes above.

---

### Idea 3 — Glass Box (audit / replay / EU AI Act)
| Dim | Score | Why |
| --- | --- | --- |
| Prevalence | 3 | Only *high-risk / regulated* deployments — but within that segment, adoption is **100% (mandatory)**. |
| Severity | 4 | Ship-blocker + fines up to **€35M or 7% of global turnover.** |
| Fit | 3 | Session recording is a strong enabler, but a real audit trail needs a structured event layer built on top. |
| Tailwind | 5 | **Highest** — a hard legal deadline (EU AI Act Art. 12, phasing 2026–2027) makes the spend non-discretionary. |
| **Composite** | **3.70** | |

**Quantified anchor.** EU AI Act non-compliance fines reach **€35M or 7% of
global annual turnover**, and **Article 12 event-logging is mandatory** for
high-risk systems — not a nice-to-have. "Impact" here is binary
(ship-in-EU-or-not) for a *defined but narrower* segment. *Model confidence:
high on the mandate/fines (statutory), low on how many of Solari's near-term
users are in-scope high-risk deployers.*

---

## Ranked, descending by impact

| Rank | Idea | Composite | One-line quantified impact |
| --- | --- | --- | --- |
| **1** | **Best-of-N on Real State** (reliability) | **4.70** | Turns ~36% → ~99% task success; attacks the #1 reason **40%** of agent projects are projected to be canceled. |
| **2** | **Untrusted-Code Gateway** (RCE) | **4.50** | Contains **CVSS 9.6** RCE classes; one prevented breach ≈ **~$4.4M**; ~100% of code-running agents exposed. |
| **3** | **Quarantine Browser** (prompt injection) | **4.15** | Drives residual **11.2% → ~0%** attack success on the **OWASP #1** agent risk. |
| **4** | **Freeze & Hand Off** (HITL + idle cost) | **4.10** | Modeled **~40–60%** environment-cost cut on handoff-heavy workloads; rides the 5×-by-2028 cost curve. |
| **5** | **Glass Box** (audit / EU AI Act) | **3.70** | Unlocks EU high-risk deployment; avoids fines up to **7% of global turnover** — but a narrower segment. |

---

## Reading the ranking

- **#1 (reliability) wins on impact** because it's the only idea that scores 5 on
  *both* prevalence and severity: it's universal **and** it's the specific
  failure that kills projects — the largest addressable market signal in the
  data (40% cancellation, 95% no-P&L). Its only soft spot is Fit (needs a
  verifier and costs N× tokens on gated steps), but Solari's cheap fast forks are
  precisely what makes the technique economical, so it also best *showcases
  Solari's architecture*.
- **#2 (RCE) is the safest high-severity pick** — the one place Solari's core
  primitive (a disposable microVM) is the literal textbook fix, so Fit = 5. It
  loses to #1 only on prevalence (coding agents are a subset).
- **#5 (audit) has the strongest single tailwind** (a legal deadline) but the
  narrowest reach, which is why a broad-impact ranking puts it last despite the
  scariest headline fine.

### Two caveats on this ranking
1. **Weights are a choice.** If you weight *spend-readiness* higher (bet on
   "budget that must be spent"), Glass Box climbs. If you weight *Fit* higher
   (bet on "cleanest Solari demo"), the RCE Gateway can tie or pass reliability.
   The model is transparent so you can re-weight and re-rank.
2. **This ranks market impact, which is what you asked.** For the *hiring
   challenge* specifically there's a second lens — demoability / "wow in 90
   seconds" — where #1 and #4 shine brightest (a visibly flattened p^N curve; a
   live freeze→VNC-takeover→resume). If you want, the next step is to re-score on
   that second axis and pick where the two rankings agree.

**Bottom line:** by market impact, **Best-of-N on Real State (reliability)** is
the top pick, with the **Untrusted-Code Gateway (RCE)** a close, lower-risk
second.
