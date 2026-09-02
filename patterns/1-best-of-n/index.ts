/**
 * Best-of-N on Real State — a reliability harness against compounding error.
 * ---------------------------------------------------------------------------
 * WHY THIS EXISTS
 *
 * An agent that succeeds at each step with probability p succeeds end-to-end
 * with only p^N over N steps. At p=0.95 that is 0.36 by step 20 — you cannot
 * prompt your way out of an exponential. (Sources cited in README.md.)
 *
 * Everyone already does best-of-N on *text* (sample k completions, keep the
 * best). Almost nobody does it on *live environment state*, because forking a
 * real machine mid-run is normally too expensive to do per step. On Solari it
 * is cheap: a microVM boots from a memory snapshot in ~1s, so we can
 *
 *     checkpoint  ->  fork N  ->  run the fragile step N ways in parallel
 *                 ->  VERIFY each fork's real filesystem state
 *                 ->  keep the one that passes, snapshot it forward
 *                 ->  on all-fail, roll back to the checkpoint and retry.
 *
 * A bad step never propagates, so the p^N curve visibly flattens.
 *
 * ---------------------------------------------------------------------------
 * SDK VERIFICATION NOTE (read before trusting the method names below)
 *
 * Snapshot / fork / revert / volume method names were confirmed against
 * https://docs.getsolari.com/snapshots , /volumes and /sdk/typescript/sandboxes
 * (Sep 2026), NOT against a live API key. Confirmed surface used here:
 *
 *   client.sandboxes.create({ template, fromSnapshot?, volumes? })  -> Sandbox
 *   sandbox.snapshot(name?)            -> Promise<string>  (snapshot id)
 *   sandbox.revert(snapshotId)         -> Promise<void>    (rewind SAME VM)
 *   sandbox.connect() / kill()
 *   sandbox.commands.run(cmd, { args })-> { exitCode, stdout, stderr }
 *   sandbox.files.write / readText / list
 *   client.volumes.create({ name })    -> { volumeId }     (see TODO below)
 *
 * "Fork" is NOT a method — it is create({ fromSnapshot }). We wrap it in a
 * fork() helper below so the intent is obvious and there is one place to fix
 * if the surface differs. Anything still uncertain is flagged `TODO: verify`.
 */

import { SolariClient } from "@solarisdk/sdk"

// --------------------------------------------------------------------------
// Tunables. Defaults are chosen so the demo tells a clear story; override via
// env to explore the p^N curve yourself.
// --------------------------------------------------------------------------
const SEED = Number(process.env.DEMO_SEED ?? 98) // deterministic flakiness (see below)
const N_STEPS = Number(process.env.DEMO_STEPS ?? 12) // length of the fragile pipeline
const N_FORKS = Number(process.env.DEMO_FORKS ?? 3) // the "N" in best-of-N
const P_STEP = Number(process.env.DEMO_P ?? 0.65) // per-attempt success probability
const MAX_RETRIES = Number(process.env.DEMO_RETRIES ?? 4) // rollback+retry budget per step

const WORK_LOG = "/work/pipeline.log" // in-VM working state (copy-on-write per fork)
const DATA_LOG = "/data/pipeline.log" // durable, EXTERNAL state (on the volume)

// --------------------------------------------------------------------------
// Deterministic "flakiness". A real fragile step fails stochastically; to keep
// the demo reproducible we decide failure HOST-side from a seeded hash of
// (step, fork, retry). Same inputs -> same outcome every run, so the console
// output is stable and reviewable. Crucially the *failure is real*: a
// "misbehaving" attempt writes a genuinely wrong marker onto the sandbox
// filesystem, and the verifier catches it by re-reading that filesystem.
// --------------------------------------------------------------------------
function hashUnit(seed: number, step: number, fork: number, retry: number): number {
  // FNV-1a over the coordinate string, then a mulberry32 finalizer -> [0,1).
  let h = 2166136261 >>> 0
  const s = `${seed}:${step}:${fork}:${retry}`
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  h += 0x6d2b79f5
  let t = h
  t = Math.imul(t ^ (t >>> 15), t | 1)
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296
}
// Would this attempt do its job correctly, or corrupt the state?
const attemptSucceeds = (step: number, fork: number, retry: number): boolean =>
  hashUnit(SEED, step, fork, retry) < P_STEP

// The correct output of step `s`. The verifier demands exactly this on disk.
const expectedMarker = (step: number) => `STEP-${step}-OK`

// --------------------------------------------------------------------------
// The one place that knows "fork" == "create from a snapshot". If Solari ever
// ships a dedicated .fork(), change only this.
// TODO: verify against Solari SDK — confirmed as create({ fromSnapshot }) from
// docs.getsolari.com/snapshots, not yet run against a live key.
// --------------------------------------------------------------------------
async function fork(client: SolariClient, snapshotId: string, volumeId: string) {
  return client.sandboxes.create({
    template: "base",
    fromSnapshot: snapshotId, // boot a fresh, independent copy of the checkpoint
    // Mount the durable volume. Forks READ prior state from their own
    // copy-on-write filesystem (carried by the snapshot); only the *winner*
    // writes to the shared volume, so concurrent forks never collide.
    volumes: [{ volumeId, path: "/data" }],
  })
}

/**
 * Run one step of the pipeline inside a single (already-connected) sandbox.
 * Appends this step's marker to the in-VM working log. Note the step ALWAYS
 * exits 0 even when it corrupts state — modelling the common, nastier failure
 * mode where a tool call "succeeds" operationally but produces a wrong result.
 * That is exactly why we verify real state instead of trusting exit codes.
 */
async function runStep(sandbox: any, step: number, fork: number, retry: number) {
  const marker = attemptSucceeds(step, fork, retry)
    ? expectedMarker(step)
    : `STEP-${step}-CORRUPT` // a real, wrong artifact on the filesystem

  // commands.run is NOT shell-interpreted, so we invoke sh explicitly for the
  // append redirection. (Marker is a fully controlled, injection-free string.)
  await sandbox.commands.run("sh", {
    args: ["-c", `printf '%s\\n' "${marker}" >> ${WORK_LOG}`],
  })
}

/**
 * The verifier. This is the heart of the pattern: it does NOT trust the step's
 * return value — it re-reads the resulting filesystem state and checks it is
 * internally consistent (right number of lines) AND correct (right last line).
 * A text-match on the model's claim would not have caught the CORRUPT write.
 */
async function verifyStep(sandbox: any, step: number): Promise<boolean> {
  const text: string = await sandbox.files.readText(WORK_LOG)
  const lines = text.split("\n").filter((l) => l.length > 0)
  const cumulativeIntegrity = lines.length === step + 1 // no dropped/duplicated steps
  const lastCorrect = lines[lines.length - 1] === expectedMarker(step)
  return cumulativeIntegrity && lastCorrect
}

// --------------------------------------------------------------------------
// Establish the initial checkpoint: an empty pipeline log on a fresh VM.
// Returns the snapshot id every step will fork from at step 0.
// --------------------------------------------------------------------------
async function initCheckpoint(client: SolariClient, volumeId: string): Promise<string> {
  const sbx = await client.sandboxes.create({
    template: "base",
    volumes: [{ volumeId, path: "/data" }],
  })
  try {
    await sbx.connect()
    await sbx.commands.run("mkdir", { args: ["-p", "/work"] })
    await sbx.commands.run("sh", { args: ["-c", `: > ${WORK_LOG}`] }) // truncate/create empty
    // Snapshot = named save point we can fork or rewind to later. Returns a
    // string id; the VM keeps running (we kill it because we only wanted the id).
    const snap: string = await sbx.snapshot("checkpoint-init")
    return snap
  } finally {
    await sbx.kill() // snapshot persists independently of this VM
  }
}

// --------------------------------------------------------------------------
// BASELINE: a naive linear agent. One VM, one attempt per step, no verify-driven
// retry. It stops the instant a step produces bad state — which is what p^N
// guarantees will happen early.
// --------------------------------------------------------------------------
async function runLinear(client: SolariClient, checkpoint: string, volumeId: string) {
  console.log("\n=== BASELINE: linear agent (1 attempt/step, no fork, no rollback) ===")
  const sbx = await fork(client, checkpoint, volumeId)
  try {
    await sbx.connect()
    for (let step = 0; step < N_STEPS; step++) {
      await runStep(sbx, step, /*fork*/ 0, /*retry*/ 0)
      const ok = await verifyStep(sbx, step)
      console.log(`  step ${String(step).padStart(2)}: ${ok ? "ok" : "BAD STATE"}`)
      if (!ok) {
        console.log(`  linear run: FAILED at step ${step} (bad state propagated, run aborted)`)
        return { passed: false, failedAt: step }
      }
    }
    console.log("  linear run: PASSED")
    return { passed: true, failedAt: -1 }
  } finally {
    await sbx.kill()
  }
}

// --------------------------------------------------------------------------
// THE HARNESS: best-of-N on real state.
// --------------------------------------------------------------------------
async function runBestOfN(client: SolariClient, checkpoint: string, volumeId: string) {
  console.log(`\n=== HARNESS: best-of-${N_FORKS} (checkpoint -> fork -> verify -> select -> rollback) ===`)

  // `checkpoint` is our rolling "last known-good" save point. We advance it only
  // when a step is verified. On all-fail we simply DON'T advance it — that is
  // the rollback: the next retry forks from the same known-good state again.
  let currentCheckpoint = checkpoint

  for (let step = 0; step < N_STEPS; step++) {
    let committed = false

    for (let retry = 0; retry <= MAX_RETRIES && !committed; retry++) {
      // 1) FORK N independent copies of the current checkpoint, in parallel.
      const forks = await Promise.all(
        Array.from({ length: N_FORKS }, () => fork(client, currentCheckpoint, volumeId)),
      )
      try {
        await Promise.all(forks.map((f) => f.connect()))

        // 2) Run the fragile step N ways IN PARALLEL, then VERIFY each fork's
        //    real filesystem state independently.
        const results = await Promise.all(
          forks.map(async (f, forkIdx) => {
            await runStep(f, step, forkIdx, retry)
            return { forkIdx, sbx: f, ok: await verifyStep(f, step) }
          }),
        )

        const verdict = results.map((r) => (r.ok ? "PASS" : "fail")).join(",")
        const winner = results.find((r) => r.ok)

        if (winner) {
          // 3) SELECT the winner: snapshot its verified state -> new checkpoint,
          //    and persist that verified state to the EXTERNAL volume.
          currentCheckpoint = await winner.sbx.snapshot(`step-${step}-verified`)

          // Persist verified state OUTSIDE the VM. Why a volume and not the
          // orchestrator's memory/chat history? (a) it survives VM death and
          // any orchestrator restart; (b) it keeps the driving transcript short
          // — no growing blob of intermediate state to re-read every turn, which
          // is how you avoid "context rot" degrading a long agent run.
          await winner.sbx.commands.run("cp", { args: [WORK_LOG, DATA_LOG] })

          const tag = retry === 0 ? "" : ` (recovered on retry ${retry})`
          console.log(
            `  step ${String(step).padStart(2)}: [${verdict}] -> keep fork ${winner.forkIdx}${tag}`,
          )
          committed = true
        } else {
          // 4) ALL forks failed -> ROLL BACK. We discard every fork and keep
          //    `currentCheckpoint` where it was; the loop re-forks from it.
          console.log(
            `  step ${String(step).padStart(2)}: [${verdict}] -> ALL FAILED, rollback to checkpoint, retry ${retry + 1}/${MAX_RETRIES}`,
          )
        }
      } finally {
        // Losers (and the winner, whose state is safe in the snapshot) are
        // billed VMs — tear them all down.
        await Promise.all(forks.map((f) => f.kill()))
      }
    }

    if (!committed) {
      console.log(
        `  best-of-${N_FORKS} run: FAILED at step ${step} after ${MAX_RETRIES} rollbacks (rolled back to last good checkpoint)`,
      )
      return { passed: false, failedAt: step, checkpoint: currentCheckpoint }
    }
  }

  console.log(`  best-of-${N_FORKS} run: PASSED`)
  return { passed: true, failedAt: -1, checkpoint: currentCheckpoint }
}

// --------------------------------------------------------------------------
async function main() {
  if (!process.env.SOLARI_API_KEY) {
    throw new Error("Set SOLARI_API_KEY (see .env.example). Get a key at https://console.getsolari.com")
  }

  // SolariClient defaults baseUrl to https://api.getsolari.com.
  const client = new SolariClient({ apiKey: process.env.SOLARI_API_KEY })

  console.log(
    `Config: seed=${SEED} steps=${N_STEPS} forks=${N_FORKS} p/step=${P_STEP} maxRetries=${MAX_RETRIES}`,
  )
  console.log(`Naive end-to-end odds if we just retried nothing: p^N = ${(P_STEP ** N_STEPS).toFixed(4)}`)

  // Durable external state lives on a volume. One volume, re-attached to every
  // fork; only verified state is ever written to it.
  // TODO: verify against Solari SDK — the umbrella client exposes `.volumes`
  // (per docs.getsolari.com/sdk/typescript); some docs show `sandboxes.volumes`.
  // If `client.volumes` is wrong, switch to `client.sandboxes.volumes`.
  const vol = await client.volumes.create({ name: `best-of-n-${Date.now()}` })
  const volumeId: string = vol.volumeId

  const checkpoint = await initCheckpoint(client, volumeId)

  // Same deterministic flakiness feeds both runs, so the comparison is apples
  // to apples: the linear run's single attempt at each step is exactly fork 0 /
  // retry 0 of the harness.
  const linear = await runLinear(client, checkpoint, volumeId)
  const best = await runBestOfN(client, checkpoint, volumeId)

  console.log("\n=== RESULT ===")
  console.log(
    `  linear    : ${linear.passed ? "PASSED" : `FAILED at step ${linear.failedAt}`}`,
  )
  console.log(
    `  best-of-${N_FORKS} : ${best.passed ? "PASSED" : `FAILED at step ${best.failedAt}`}`,
  )
  console.log(
    "  The reliability lift comes from never letting a bad step propagate:",
  )
  console.log(
    "  fork -> verify real state -> keep the winner -> roll back on all-fail.",
  )

  if (best.passed) {
    // Show the verified state really lives outside any single VM: re-attach the
    // volume to a brand-new sandbox and read it back.
    const reader = await client.sandboxes.create({
      template: "base",
      volumes: [{ volumeId, path: "/data" }],
    })
    try {
      await reader.connect()
      const persisted = await reader.files.readText(DATA_LOG)
      console.log(`\n  Verified state persisted on the volume (${persisted.split("\n").filter(Boolean).length} steps):`)
      console.log(persisted.trim().split("\n").map((l) => `    ${l}`).join("\n"))
    } finally {
      await reader.kill()
    }
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
