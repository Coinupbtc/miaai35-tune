#!/usr/bin/env python3
"""PP-focused bench for llama-miaai35: prompt-processing speed + TTFT at agent-scale
prompt sizes, plus a decode/quality coding probe. Uses llama-server's own `timings`
object (exact, server-side) rather than client-side estimation.

Usage: python3 bench_pp.py --tag mytag [--runs 3]
Writes results/pp-<tag>-<stamp>.json and prints a markdown table.
"""
import argparse, json, statistics, time, urllib.request, datetime, pathlib, subprocess

import os
BASE = os.environ.get("MIA_BASE", "http://127.0.0.1:8889")
MODEL = "$HOME/models/dgx_bundle/qwen3.6-35b-a3b-ud/Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf"

# Deterministic natural-text filler (~1.3 tok/word) that varies per salt so the
# KV prefix cache cannot serve repeat runs.
VOCAB = ("service restarted cleanly after the watchdog noticed elevated latency on "
         "the inference endpoint and the operator confirmed memory pressure was "
         "within budget while the scheduler continued dispatching agent tasks "
         "normally across profiles during the evening maintenance window").split()

def make_prompt(n_words: int, salt: str) -> str:
    h = sum(ord(c) for c in salt)
    words = [VOCAB[(i * 13 + h + (i // 17)) % len(VOCAB)] for i in range(n_words)]
    return (
        f"[{salt}] Below are synthetic operations notes. Read them fully.\n"
        + " ".join(words)
        + "\nQuestion: In one short sentence, what kind of text is above?"
    )

CODING_PROMPT = (
    "Write a Python function `merge_intervals(intervals)` that merges overlapping "
    "[start,end] intervals, with type hints, docstring, and 3 doctest examples. "
    "Then briefly explain its time complexity."
)

def chat(prompt: str, max_tokens: int, timeout: int = 300):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "timings_per_token": False,
    }).encode()
    req = urllib.request.Request(
        BASE + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    wall = time.time() - t0
    t = d.get("timings", {})
    return {
        "wall_s": round(wall, 3),
        "prompt_n": t.get("prompt_n"),
        "pp_tps": round(t.get("prompt_per_second") or 0, 1),
        "ttft_s": round((t.get("prompt_ms") or 0) / 1000, 3),
        "gen_n": t.get("predicted_n"),
        "gen_tps": round(t.get("predicted_per_second") or 0, 2),
        "content": (d["choices"][0]["message"].get("content") or "")[:400],
    }

def busy_slots() -> int:
    try:
        with urllib.request.urlopen(BASE + "/slots", timeout=5) as r:
            return sum(1 for s in json.load(r) if s.get("is_processing"))
    except Exception:
        return -1

def vram_mib() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=process_name,used_memory",
             "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "llama-server" in line:
                return int(line.rsplit(",", 1)[1])
    except Exception:
        pass
    return -1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    results = {"tag": args.tag, "ts": datetime.datetime.now().isoformat(),
               "vram_mib": vram_mib(), "tests": {}}

    # warmup
    chat("Say OK.", 8)

    cases = [
        ("pp_8k",  make_prompt(6000,  args.tag), 32),
        ("pp_24k", make_prompt(18000, args.tag), 32),
        ("coding", CODING_PROMPT, 700),
    ]
    for name, prompt, mt in cases:
        runs = []
        for i in range(args.runs):
            b = busy_slots()
            # salt per-run for pp cases so KV prefix cache can't serve run 2/3
            p = prompt if name == "coding" else make_prompt(
                6000 if name == "pp_8k" else 18000, f"{args.tag}-r{i}")
            r = chat(p, mt)
            r["busy_slots_before"] = b
            runs.append(r)
            print(f"{name} run{i+1}: prompt_n={r['prompt_n']} pp={r['pp_tps']} t/s "
                  f"ttft={r['ttft_s']}s gen={r['gen_tps']} t/s busy={b}", flush=True)
        med = lambda k: statistics.median(x[k] for x in runs if x[k] is not None)
        results["tests"][name] = {
            "runs": runs,
            "median": {k: med(k) for k in ("pp_tps", "ttft_s", "gen_tps", "wall_s")},
        }

    results["vram_mib_after"] = vram_mib()
    out = pathlib.Path(__file__).parent / "results" / (
        f"pp-{args.tag}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")
    print(f"\n| Test | median PP t/s | median TTFT | median gen t/s |")
    print(f"|---|---:|---:|---:|")
    for name, t in results["tests"].items():
        m = t["median"]
        print(f"| {name} | {m['pp_tps']} | {m['ttft_s']}s | {m['gen_tps']} |")
    print(f"\nVRAM llama-server: {results['vram_mib']} -> {results['vram_mib_after']} MiB")

if __name__ == "__main__":
    main()
