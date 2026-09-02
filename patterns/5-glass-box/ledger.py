"""The decision ledger: an append-only, hash-chained JSON-lines event log.

WHY hash-chained. EU AI Act Article 12 asks for logs that are automatically
recorded AND resistant to after-the-fact tampering
(https://artificialintelligenceact.eu/article/12/). A plain log file can be
silently edited. Chaining each record's hash into the next (like a tiny
blockchain / Merkle chain) makes any edit or deletion detectable: change one
record and every hash after it no longer verifies. This is event-sourcing — the
run is the ordered list of immutable events, and it is the source of truth.

Schema per line (one JSON object):
    ts       ISO-8601 UTC timestamp (when the event occurred)
    run_id   which run this belongs to
    step     monotonically increasing index within the run
    action   what happened: run_start | browser_launch | tool_call | extract |
             decision | approval | replay_download | run_end
    inputs   what went in (JSON)
    outcome  what came out (JSON)
    prev     hash of the previous record (chain link)
    hash     sha256(prev + canonical(this record without `hash`))
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _canonical(obj: dict) -> str:
    """Stable serialization so hashes are reproducible across machines."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(prev: str, payload: dict) -> str:
    return hashlib.sha256((prev + _canonical(payload)).encode("utf-8")).hexdigest()


class EventLog:
    """Append-only writer. Every emit() flushes immediately (log-as-you-go)."""

    def __init__(self, path, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self._prev = GENESIS
        self._step = 0
        # Fresh artifact per run.
        self.path.write_text("", encoding="utf-8")

    def emit(self, action: str, inputs=None, outcome=None) -> dict:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "step": self._step,
            "action": action,
            "inputs": inputs or {},
            "outcome": outcome or {},
            "prev": self._prev,
        }
        rec = dict(payload, hash=_hash(self._prev, payload))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(rec) + "\n")
        self._prev = rec["hash"]
        self._step += 1
        return rec


def load_log(path) -> list:
    """Read a ledger back and VERIFY the hash chain.

    Raises ValueError on any break — a broken chain means the audit log was
    tampered with (or truncated), which under Article 12 is itself a finding.
    """
    records = []
    prev = GENESIS
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        stored = rec.get("hash")
        payload = {k: rec[k] for k in rec if k != "hash"}
        if rec.get("prev") != prev:
            raise ValueError(f"{path}:{lineno}: broken chain (prev mismatch)")
        if _hash(prev, payload) != stored:
            raise ValueError(f"{path}:{lineno}: tampered record (hash mismatch)")
        records.append(rec)
        prev = stored
    return records
