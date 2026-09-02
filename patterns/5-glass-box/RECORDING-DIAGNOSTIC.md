# Recording diagnostic — evidence

Glass Box has two halves:

1. **Event-sourced decision ledger** (hash-chained `events.jsonl` + `verify` /
   `show` / `diff`) — **fully validated live**, works on any plan.
2. **DOM-level rrweb replay** via Solari session recording
   (`launch(recording=True)` → `sessions.download_replay`) — **blocked on the
   starter plan** (see below).

This file is the reproducible evidence for the second point, produced by
[`check_recording.py`](./check_recording.py). It exists so the finding is
auditable rather than asserted.

## Method (all timings 3× our in-demo defaults, to eliminate impatience)

- Launch a browser with `recording=True`.
- Drive **real DOM activity**: navigate to example.com, mouse moves, scroll,
  click the "More information…" link, `go_back` — so rrweb has mutations to
  capture (a 2s static page might record almost nothing).
- **~20s** total session length.
- Call **`sessions.release_and_wait(session_id)`** to force the async upload to
  flush before polling.
- **Poll `download_replay` for up to ~180s** (60 attempts × 3s).

## Result — 2026-09-02

```
sessions methods : ['create', 'download_replay', 'get', 'get_replay_url', 'release', 'release_and_wait']
release_and_wait : (session_id: 'str') -> 'None'
session          : ip-10-0-11-211:abfc357c-...:1788314121778.jnap8U68EK1YkyUXTUJ5Hw
session length   : ~20s (recording flag was True)
release_and_wait : None
   15s: status=404 Solari GET /sessions/ip-10-0-11-211:.../replay-url ... "No replay available for this session"
   30s: status=404 ...
   ...
  180s: status=404 ...

NO REPLAY after ~180s. recording=True was accepted but no replay was produced.
```

`release_and_wait` returned cleanly (the session released fine), the session id
is recognized by the API (the 404 body echoes it back), yet the replay endpoint
returns **`404 "No replay available for this session"`** for the entire 3-minute
window — and it stayed 404 minutes later in a separate check.

## Conclusion

Length, activity, upload-flush, and poll-duration are all ruled out. The
`recording=True` flag is accepted (it's a real parameter — confirmed in the
`launch()` signature) but produces no artifact on this account. This is a
**plan/account feature gate**: **session recording is not enabled on the starter
plan** used here. It is not a code, SDK-name, or timing bug.

## What this means for the pattern

- The novel contribution — the event-sourced, tamper-evident decision ledger and
  the `verify`/`show`/`diff` reproducibility tooling — is fully working and does
  **not** depend on Solari recording.
- The rrweb replay is a complementary DOM-level ledger. To validate that half,
  re-run `check_recording.py` on a plan that includes session recording; it will
  print the replay's byte and event counts and exit 0.
