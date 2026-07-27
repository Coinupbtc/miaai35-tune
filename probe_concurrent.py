#!/usr/bin/env python3
"""Multi-agent starvation probe: while a large prompt (~14k tok) is being
prompt-processed in one slot, measure TTFT and decode t/s of a small chat in
another slot. This is the metric that matters for multi-agent feel.

Usage: python3 probe_concurrent.py --tag ub2048 [--runs 3]
"""
import argparse, json, statistics, threading, time, urllib.request
from bench_pp import make_prompt, chat, busy_slots

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    chat("Say OK.", 8)  # warmup
    ttfts, gens = [], []
    for i in range(args.runs):
        big_prompt = make_prompt(18000, f"probe-{args.tag}-{i}")
        bg_result = {}
        t = threading.Thread(target=lambda: bg_result.update(chat(big_prompt, 16)))
        t.start()
        time.sleep(1.0)  # let PP start
        small = chat("Count from 1 to 30, comma separated, nothing else.", 80)
        t.join()
        ttfts.append(small["ttft_s"]); gens.append(small["gen_tps"])
        print(f"run{i+1}: small TTFT={small['ttft_s']}s gen={small['gen_tps']} t/s "
              f"(bg pp={bg_result.get('pp_tps')} t/s) busy_now={busy_slots()}", flush=True)
    print(f"\n[{args.tag}] median small-chat during big PP: "
          f"TTFT={statistics.median(ttfts)}s gen={statistics.median(gens)} t/s")

if __name__ == "__main__":
    main()
