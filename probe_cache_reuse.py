#!/usr/bin/env python3
"""Cache-reuse probe: agent-style repeat call where the prompt HEADER changes
(timestamp/code word) but the large body is identical. Without --cache-reuse the
whole prompt reprocesses from the first changed token; with it, unchanged KV
chunks shift. Measures repeat-call TTFT and checks a canary fact so reused KV
cannot serve stale content undetected.

Usage: python3 probe_cache_reuse.py --tag v2-noreuse [--runs 3]
"""
import argparse, statistics
from bench_pp import make_prompt, chat

def build(salt: str, code: str, head: str, tail: str) -> str:
    # agent-shaped: constant system header (slot LCP match), small CHANGING
    # status block mid-prompt, large constant tail after it (reuse candidate).
    return (
        f"You are an operations assistant. Fixed policy preamble follows.\n{head}\n"
        f"--- LIVE STATUS (changes every call) ts={salt} | code word: {code} ---\n"
        f"--- ARCHIVED NOTES (unchanged) ---\n{tail}\n"
        f"--- END ---\n"
        f"Reply with ONLY the code word from the live status line."
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    chat("Say OK.", 8)  # warmup
    colds, warms, canaries = [], [], []
    for i in range(args.runs):
        head = make_prompt(1500, f"head-{args.tag}-{i}")   # ~2k tok constant prefix
        tail = make_prompt(7000, f"tail-{args.tag}-{i}")   # ~7.5k tok constant tail
        r1 = chat(build(f"2026-07-09T21:0{i}", f"ALPHA{i}", head, tail), 16)
        # only the mid-prompt status block changes -> prefix matches slot,
        # tail is the KV-shift reuse candidate
        r2 = chat(build(f"2026-07-09T22:1{i}", f"OMEGA{i}", head, tail), 16)
        ok = f"OMEGA{i}" in (r2["content"] or "").upper()
        colds.append(r1["ttft_s"]); warms.append(r2["ttft_s"]); canaries.append(ok)
        print(f"run{i+1}: cold TTFT={r1['ttft_s']}s (pp_n={r1['prompt_n']}) | "
              f"repeat TTFT={r2['ttft_s']}s (pp_n={r2['prompt_n']}) | "
              f"canary fresh={ok} got={r2['content']!r}", flush=True)
    print(f"\n[{args.tag}] median cold={statistics.median(colds)}s "
          f"repeat={statistics.median(warms)}s "
          f"canary {sum(canaries)}/{len(canaries)} fresh")

if __name__ == "__main__":
    main()
