# solari-cookbook — Technical Breakdown

Cloned to `./solari-cookbook` (not run). This is a **cookbook**: a set of tiny,
self-contained, runnable examples for the Solari platform. There is no library
source here — the examples consume Solari's published SDK packages from
npm/PyPI. Each example is one idea, ~30–70 lines, with the surprising bits
documented in inline comments.

## What Solari is

A single API (one `slr_live_...` key, one billing balance) that gives you three
cloud primitives:

- **Cloud browser** — a Playwright/Puppeteer-compatible browser running on
  Solari's infra instead of your machine. Adds stealth fingerprinting, managed
  residential proxies, captcha solving, persistent profiles, and session
  recording.
- **Sandbox** — a headless Linux **microVM** that boots from a memory snapshot
  in ~1s. For running untrusted/LLM-generated code, builds, data jobs. Isolated
  from your machine and other tenants.
- **Desktop** — a sandbox **with a screen**: same microVM + X11 + a live VNC
  stream. For computer-use agents and GUI apps.

Base API URL: `https://api.getsolari.com`. Preview URLs are served from
`*.preview.getsolari.com`.

## Repo layout

```
solari-cookbook/
├── README.md            # product overview + "gotchas" section
├── LICENSE (MIT)
└── examples/
    ├── browser-quickstart-ts/          launch → open page → read → close
    ├── browser-quickstart-py/          same, Python
    ├── browser-stealth-proxy-ts/       stealth + residential proxy egress
    ├── browser-profiles-ts/            persistent cookies/localStorage
    ├── browser-session-recording-py/   rrweb replay capture + download
    ├── sandbox-quickstart-ts/          run cmd, write/read files
    ├── sandbox-code-interpreter-py/    stateful Python kernel (agent loop)
    ├── sandbox-port-preview-ts/        expose in-VM server on public URL
    └── desktop-computer-use-py/        screenshot/click/type on Linux GUI
```

Each dir is self-contained: `.env.example`, a README, and either
`package.json` (+`index.ts`, run with `tsx`) or `requirements.txt`
(+`main.py`). All async.

## SDK packages in play

| Package (npm) | Package (PyPI) | Used for |
| --- | --- | --- |
| `@solarisdk/browser` | `solari-browser` | Cloud browser (`Solari` class) |
| `@solarisdk/sdk` | — | Umbrella `SolariClient`; defaults `baseUrl` |
| `@solarisdk/sdk` (sandbox) | `solari-sandbox` | Standalone `SandboxClient` |
| — | `solari-desktop` | Standalone `DesktopClient` |

Key detail: the **umbrella `SolariClient`** defaults `baseUrl` to
`https://api.getsolari.com`; the **standalone** `SandboxClient`/`DesktopClient`
require `base_url`/`baseUrl` explicitly.

## API surface, by product

### Cloud browser — `Solari` / `solari.launch()`
- `const browser = await solari.launch(opts)` — creates a session **and**
  connects a Playwright-compatible browser in one call. After that it's plain
  Playwright: `browser.newPage()`, `page.goto()`, `page.locator(...).innerText()`.
- `browser.id` — session id.
- **`launch()` options**: `stealth: true` (fingerprint patches + headful browser
  on real GPU), `proxy` (`"us"`, `{ country, tier: "mobile", session: "warm-1" }`,
  or `"smart"`), `captcha: true`, `profileId`, `recording: true`.
  `proxy` and `captcha` **require** `stealth: true`.
- `browser.proxy` — what the gateway resolved (country/tier/tz), never upstream creds.
- **Profiles**: `solari.profiles.list() / create({name}) / save(id, storageState)`
  — server-side cookies+localStorage; attach via `profileId`. Saving is manual;
  attaching does not auto-persist.
- **Recording**: `solari.sessions.download_replay(sessionId)` → gzipped rrweb
  **NDJSON** (DOM-level, not video). HTTP client auto-decompresses (don't gunzip
  yourself). Upload is async after release → first polls 404.

### Sandbox — `SolariClient.sandboxes` / `SandboxClient`
- `create({ template: "base", timeoutMs })` → `sandbox`, has `sandboxId`.
- `sandbox.connect()` — opens the control channel (needed for files/git/code;
  bare commands can use a one-shot HTTP path without it).
- `sandbox.commands.run(cmd, { args })` — **NOT shell-interpreted**; argv in
  `args`; waits for exit (background long-running procs with `sh -c '... &'`).
  Returns `{ exitCode, stdout, ... }`.
- `sandbox.files.write(path, data) / readText(path) / list(dir)`.
- `sandbox.create_code_context("python")` + `sandbox.run_code(src, context_id)`
  — **stateful kernel**; vars/imports persist across calls (notebook-style, for
  agent loops). Output is `result.results` (items typed `stdout`/`stderr`/`result`
  + png/svg/html), plus `result.error`. No top-level `.stdout`.
- `sandbox.previewUrl(port)` → public `*.preview.getsolari.com` URL.
- `sandbox.kill()` destroys the VM. `close()` alone only drops the local channel.

### Desktop — `DesktopClient`
- `create({ template: "default", resolution, timeoutMs })` → `desktop`, has
  `sessionId` and `streamUrl` (embeddable VNC).
- `connect()`, then poll `desktop.health().ready` until X11 is up.
- `desktop.open(appName)` → pid (default image: mousepad, thunar, Chrome,
  VS Code, LibreOffice; `open()` fails if the binary's missing).
- `desktop.mouse.click(x, y, { humanize })`, `desktop.keyboard.type(text)`,
  `desktop.screenshot({ format: "png" })` → bytes.
- Teardown: `desktop.close()` (local channel) **then** `client.destroy(sessionId)`.

## Cross-cutting "gotchas" the examples encode

1. **TS browser: you must `await solari.close()`** — the client keeps a loopback
   proxy open for retries; skip it and the Node process hangs forever.
2. **`browser.close()` also releases the session** — use try/finally (or
   `await using` on Node 22+).
3. **Recording is per-session** (`recording: true` at create); no account switch.
   Replay uploads async → poll ~30s before giving up.
4. **Sandbox commands aren't shell-interpreted** — argv in `args`, or run `sh -c`.
5. **`kill()`/`destroy()` end a VM; `close()` doesn't** — VMs linger to idle timeout.
6. **`timeoutMs` is a rolling idle window**, reset on each use — not a hard deadline.

## Lifecycle pattern (common to all three)

`create/launch → connect → do work → (try/finally) kill/destroy + close`.
Everything is resource-oriented with explicit teardown, because each session is
a billed remote VM/browser slot.

## Takeaways for the challenge build

- The three primitives compose naturally into a **computer-use / coding-agent**
  story: browse (browser) → generate & run code (sandbox code interpreter) →
  preview the result on a public URL (port preview) → or drive a GUI (desktop).
- Sandbox `run_code` (stateful kernel) + `previewUrl` is the strongest base for
  an "agent that builds something you can click" demo.
- Playwright compatibility means most existing browser-automation code drops in
  with only the `launch()` swap.
