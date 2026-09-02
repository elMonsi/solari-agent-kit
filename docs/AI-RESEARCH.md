# Autonomous AI Agents (2025–2026): The Biggest Unsolved Problems

Sourced synthesis backing the build ideas in `IDEAS.md`. Scope: LLM agents that
take real actions — browse the web, run code, drive computers/desktops. A
handful of 2026-dated items are flagged **[unverified]**.

Two threads run through everything: **agents can't reliably separate trusted
instructions from untrusted content in one context window** (the safety
problems), and **stochastic per-step behavior compounds badly over long
horizons** (the reliability problems).

---

## 1. Prompt injection → dangerous actions; untrusted-code RCE

### 1a. Indirect prompt injection in action-taking agents
Attackers embed natural-language commands in pages/emails/docs; the agent
executes them with the user's authenticated session. Same-origin/CORS don't help
— the payload is language, not code.
- Brave vs. Perplexity Comet account takeover — https://brave.com/blog/comet-prompt-injection/
- "Google Drive Wiper" zero-click — https://thehackernews.com/2025/12/zero-click-agentic-browser-attack-can.html
- ChatGPT Atlas omnibox injection — https://thehackernews.com/2025/10/chatgpt-atlas-browser-can-be-tricked-by.html
- Claude for Chrome mitigations only cut attack success 23.6% → 11.2% — https://claude.com/blog/claude-for-chrome
- OpenAI: injection "unlikely to ever be fully solved" **[unverified]** — https://techcrunch.com/2025/12/22/openai-says-ai-browsers-may-always-be-vulnerable-to-prompt-injection-attacks/

**Fix:** trust boundary (dual-LLM privileged/quarantined), token provenance,
per-action confirmation for destructive/authenticated ops, VM/browser isolation.

### 1b. Untrusted code/config → RCE
Opening an untrusted repo or connecting to a malicious MCP server can trigger
command execution before any trust prompt fires.
- CurXecute CVE-2025-54135 — https://thehackernews.com/2025/08/cursor-ai-code-editor-fixed-flaw.html
- mcp-remote CVE-2025-6514 (CVSS 9.6) — https://thehackernews.com/2025/07/critical-mcp-remote-vulnerability.html
- MCP Inspector CVE-2025-49596 — https://thehackernews.com/2025/07/critical-vulnerability-in-anthropics.html
- Claude Code CVE-2025-59536 — https://thehackernews.com/2026/02/claude-code-flaws-allow-remote-code.html

**Fix:** sandboxed least-privilege execution, allowlists not denylists,
signed/pinned config, trust prompts before any code/network call.

---

## 2. Data exfiltration & credential handling
Agents holding real access (OAuth, API keys, `.env`, sessions) get induced to
leak data, often zero-click, via allowlisted/model-controlled channels.
- EchoLeak CVE-2025-32711 (M365 Copilot) — https://thehackernews.com/2025/06/zero-click-ai-vulnerability-exposes.html
- ForcedLeak (Salesforce Agentforce; expired allowlisted domain bought for ~$5) — https://thehackernews.com/2025/09/salesforce-patches-critical-forcedleak.html
- ShadowLeak (leaks from OpenAI's cloud, invisible to DLP) — https://thehackernews.com/2025/09/shadowleak-zero-click-flaw-leaks-gmail.html
- CometJacking — https://thehackernews.com/2025/10/cometjacking-one-click-can-turn.html
- AgentFlayer (Black Hat 2025) — https://thehackernews.com/2025/08/researchers-uncover-gpt-5-jailbreak-and.html

**Fix:** information-flow control (tool output must not flow unchecked to another
tool's args/egress), decode-aware egress allowlisting, confirmation before
reading logged-in accounts.

---

## 3. Browser automation being blocked (bot detection, CAPTCHAs, datacenter IPs)
HTTP has no native way for an agent to prove identity, so sites over-block and
agents get pushed toward evasion.
- Cloudflare blocks AI crawlers by default + revives HTTP 402 "Pay Per Crawl" (Jul 1 2025) — https://blog.cloudflare.com/content-independence-day-no-ai-crawl-without-compensation/
- Web Bot Auth / "Signed Agents" (cryptographic agent identity) — https://blog.cloudflare.com/signed-agents/
- Cloudflare vs. Perplexity stealth crawling — https://blog.cloudflare.com/perplexity-is-using-stealth-undeclared-crawlers-to-evade-website-no-crawl-directives/
- Amazon C&D + CFAA suit vs. Perplexity Comet — https://techcrunch.com/2025/11/04/amazon-sends-legal-threats-to-perplexity-over-agentic-browsing/
- CAPTCHAs losing power (ChatGPT Agent clicks "I am not a robot") — https://arstechnica.com/information-technology/2025/07/openais-chatgpt-agent-casually-clicks-through-i-am-not-a-robot-verification-test/

**Fix:** cryptographic agent identity + verified-agent registries, delegated
authorization, machine-payment rails. (Solari's stealth/proxy/captcha addresses
the *practical* blocking today; the identity approach is where the field is
heading — worth acknowledging honestly.)

---

## 4. Reliability, reproducibility & statefulness
- Compounding error: p^N decay; 95%/step → 36% at 20 steps.
- METR time-horizon curve — https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/
- Kanwat, "Betting Against AI Agents in 2025" — https://utkarshkanwat.com/writing/betting-against-agents/
- Vending-Bench meltdown loops — https://arxiv.org/abs/2502.15840
- τ²-bench pass^8 < 25% — https://arxiv.org/abs/2506.07982
- Context rot — https://www.trychroma.com/research/context-rot
- Non-determinism at temp 0 (batch-invariance) — https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
- Gartner: >40% of agentic projects canceled by end-2027 — https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
- MIT NANDA: ~95% of enterprise GenAI pilots no P&L impact — https://fortune.com/2025/08/18/mit-report-95-percent-generative-ai-pilots-at-companies-failing-cfo/

**Fix:** bounded verifiable steps, external structured state, idempotent +
rollback tools, checkpointing, event-sourced replay.

---

## 5. Observability, auditability & replay
- EU AI Act Article 12 (automatic event logging, high-risk) — https://artificialintelligenceact.eu/article/12/
- OTel GenAI conventions (experimental) — https://opentelemetry.io/blog/2025/ai-agent-observability/
- ClickHouse acquires Langfuse (Jan 2026) — https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability
- Agent-as-a-Judge (trajectory-level eval) — https://arize.com/blog/agent-as-a-judge-agentic-evaluation/
- Temporal durable agent harness (event-sourced replay) — https://temporal.io/blog/temporal-agent-harness-durable-agent-infrastructure

**Fix:** event-sourced immutable capture of every turn/tool/approval, portable
trace schemas, trajectory-level evals on live traces.

---

## 6. Human-in-the-loop / handoff
Hard part = durably suspend a long run, persist full state, resume without
re-running side effects, without paying for idle.
- LangGraph interrupt()/resume — https://www.langchain.com/blog/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt
- OpenAI Agents SDK approvals — https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
- Temporal × OpenAI Agents SDK — https://www.infoq.com/news/2025/09/temporal-aiagent/
- Replit wiped a prod DB during a freeze — https://fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/

**Fix:** durable/event-sourced engines with checkpointing + a durable run ID to
reattach the human's answer, per-tool risk gating, context-rich approval UIs.

---

## 7. Cost, latency, cold-start
Pain is idle time + context reprocessing, not unit compute.
- Firecracker boots <125ms — https://firecracker-microvm.github.io/
- Modal GPU cold starts "seconds to minutes" — https://modal.com/docs/guide/cold-start
- Anthropic: agents ~4× chat tokens, multi-agent ~15× — https://www.anthropic.com/engineering/multi-agent-research-system
- "Inference paradox": cost per workflow projected ~5× through 2028 — https://www.computerworld.com/article/4210786/ai-inference-is-getting-cheaper-but-your-agents-are-getting-more-expensive.html

**Fix:** scale-to-zero + snapshot/resume to park idle agents, weight caching,
prompt caching, context compaction, per-task token/step budgets.

---

## 8. Computer-use agents (screenshot/click/type)
Unreliable on real multi-step tasks, slow/expensive per step, benchmark numbers
inflated.
- Claude 3.5 OSWorld 14.9% vs ~72% human — https://www.anthropic.com/news/3-5-models-and-computer-use
- Claude Sonnet 4.5 OSWorld 61.4% (heavy scaffolding; drops to 42% with fewer steps) — https://os-world.github.io/
- "An Illusion of Progress?" (COLM 2025) — https://arxiv.org/abs/2504.01382
- Operator bought $31.43 of eggs when asked to compare prices — https://incidentdatabase.ai/cite/1028/
- Guardio "Scamlexity" — https://guard.io/labs/scamlexity-we-put-agentic-ai-browsers-to-the-test-they-clicked-they-paid-they-failed-e6c8dfac9c7f

**Fix:** verifiable atomic steps, accessibility-tree/DOM over pixels,
deterministic guardrails on payment/irreversible actions, scoped payment
credentials, normalized live-eval harnesses.

---

## Cross-cutting infrastructure themes
1. Trust boundaries / dual-LLM + information-flow control (Problems 1, 2)
2. Sandboxing, least privilege, allowlists, signed config (Problem 1b)
3. Cryptographic agent identity + delegated auth + payment rails (Problem 3)
4. **A durable, snapshot-based pause/resume substrate** — the single primitive
   under cheap idle-parking (7), safe handoff (6), reproducible replay + audit
   (5). This is Solari's structural strength.
5. Event-sourced standardized tracing + trajectory-level eval (Problem 5)
6. Deterministic guardrails + per-action confirmation for irreversible ops (1, 6, 8)

**Two most-cited, most-current issues:** (1) prompt injection (treated as
possibly permanent), and (2) low end-to-end reliability / compounding error
(drives the "most agent projects fail" headlines).
