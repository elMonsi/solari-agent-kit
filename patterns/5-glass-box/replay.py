"""replay.py — reconstruct and diff agent runs FROM THE LEDGER, not by re-execution.

This is the whole point of Glass Box. You cannot reproduce an agent run by running
it again (LLM inference is non-deterministic even at temperature 0 —
https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/), so
"replay" here means: deterministically reconstruct what happened from the immutable
event ledger. No browser, no model, no network.

    python replay.py verify <events.jsonl>          # check the hash chain (tamper check)
    python replay.py show   <events.jsonl>          # replay the run from the log
    python replay.py diff    <a.jsonl> <b.jsonl>    # where did two runs diverge?
"""

import sys

from ledger import load_log

# Fields that are expected to differ between any two runs and are NOT semantic
# divergence: wall-clock time and the chain hashes. We ignore them when diffing
# so the diff highlights DECISIONS, not clocks.
_NOISE = {"ts", "prev", "hash", "run_id"}


def show(records: list) -> None:
    """Replay a run as a human-readable narrative, purely from the ledger."""
    for rec in records:
        head = f"[{rec['step']:>2}] {rec['action']:<15} {rec['ts']}"
        print(head)
        if rec["inputs"]:
            print(f"       in : {rec['inputs']}")
        if rec["outcome"]:
            print(f"       out: {rec['outcome']}")
    print(f"\n({len(records)} events, chain verified)")


def _semantic(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in _NOISE}


def diff(a: list, b: list) -> bool:
    """Diff two run ledgers step-by-step. Returns True if they diverged.

    Divergence in the DECISION step is the reproducibility gap made concrete:
    same task, same inputs, different outcome — and here it is, on the record.
    """
    diverged = False
    n = max(len(a), len(b))
    for i in range(n):
        ra = a[i] if i < len(a) else None
        rb = b[i] if i < len(b) else None

        if ra is None or rb is None:
            diverged = True
            side = "A" if rb is None else "B"
            present = ra or rb
            print(f"[{i:>2}] LENGTH DIVERGENCE — run {side} ends early "
                  f"(other has '{present['action']}')")
            continue

        sa, sb = _semantic(ra), _semantic(rb)
        if sa == sb:
            continue

        diverged = True
        print(f"[{i:>2}] DIVERGES at action '{ra['action']}':")
        for key in sorted(set(sa) | set(sb)):
            va, vb = sa.get(key), sb.get(key)
            if va != vb:
                print(f"       {key}:")
                print(f"         A: {va}")
                print(f"         B: {vb}")

    if not diverged:
        print("No semantic divergence — the two ledgers describe the same run.")
    else:
        print("\n=> The two runs of the SAME task took different paths. This is the "
              "gap re-execution can never close; the ledger is the only record of "
              "what each run actually did (EU AI Act Art. 12).")
    return diverged


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[0]
    try:
        if cmd == "verify":
            load_log(argv[1])  # raises on tamper
            print(f"OK - {argv[1]} chain verified, no tampering detected.")
            return 0
        if cmd == "show":
            show(load_log(argv[1]))
            return 0
        if cmd == "diff":
            if len(argv) < 3:
                print("usage: python replay.py diff <a.jsonl> <b.jsonl>")
                return 2
            return 1 if diff(load_log(argv[1]), load_log(argv[2])) else 0
    except ValueError as err:
        print(f"TAMPER DETECTED: {err}", file=sys.stderr)
        return 3

    print(f"unknown command: {cmd}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
