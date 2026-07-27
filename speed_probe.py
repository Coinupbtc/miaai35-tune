#!/usr/bin/env python3
"""Runner-agnostic streaming speed probe (works on llama.cpp AND vLLM).
Measures true TTFT (first streamed token) and decode t/s (tokens after first /
elapsed) for four workloads: short, coding, copy-heavy refactor, essay, and an
~8k-token context QA (long TTFT).

Usage: MIA_BASE=http://127.0.0.1:8001 MIA_MODEL=<id> python3 speed_probe.py --tag nvfp4 [--runs 3]
"""
import argparse, json, os, statistics, time, urllib.request

BASE = os.environ.get("MIA_BASE", "http://127.0.0.1:8889")
MODEL = os.environ.get("MIA_MODEL", "m")

code = "\n".join(
    f"def handler_{i}(payload):\n    value_{i} = payload.get('field_{i}', None)\n"
    f"    if value_{i} is None:\n        return {{'error': 'missing field_{i}', 'code': {400+i}}}\n"
    f"    return {{'result': value_{i} * {i+1}, 'handler': 'handler_{i}'}}" for i in range(12))

VOCAB = ("service restarted cleanly after the watchdog noticed elevated latency on "
         "the inference endpoint and the operator confirmed memory pressure was "
         "within budget while the scheduler continued dispatching agent tasks").split()

def filler(n, salt):
    h = sum(ord(c) for c in salt)
    return " ".join(VOCAB[(i * 13 + h + i // 17) % len(VOCAB)] for i in range(n))

CASES = {
    "short": ("In one sentence, what is a systemd timer?", 64),
    "coding": ("Write a Python function `merge_intervals(intervals)` that merges overlapping "
               "[start,end] intervals, with type hints, docstring, and 3 doctest examples. "
               "Then briefly explain its time complexity.", 700),
    "refactor": (f"Here is a Python module:\n```python\n{code}\n```\nReproduce the ENTIRE module "
                 "unchanged except: rename every `payload` parameter to `request_data`. "
                 "Output only the full code block, no commentary.", 1200),
    "essay": ("Write a vivid 500-word essay on the history of container shipping.", 800),
    "ctx8k": (None, 48),  # built per-run with fresh salt
}

def stream_chat(prompt, max_tokens):
    body = json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": max_tokens, "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time(); first = None; n = 0; usage = None
    with urllib.request.urlopen(req, timeout=600) as r:
        for raw in r:
            raw = raw.strip()
            if not raw.startswith(b"data:"):
                continue
            payload = raw[5:].strip()
            if payload == b"[DONE]":
                break
            try:
                d = json.loads(payload)
                if d.get("usage"):
                    usage = d["usage"]
                ch = d.get("choices") or []
                delta = ch[0].get("delta", {}) if ch else {}
                tok = delta.get("content") or delta.get("reasoning_content")
                if tok:
                    n += 1
                    if first is None:
                        first = time.time()
            except Exception:
                continue
    end = time.time()
    ttft = (first or end) - t0
    true_n = (usage or {}).get("completion_tokens") or n  # chunks undercount on vLLM
    dec = (true_n - 1) / (end - first) if first and end > first and true_n > 1 else 0
    return {"ttft": round(ttft, 3), "gen_tps": round(dec, 2), "chunks": true_n}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    stream_chat("Say OK.", 8)  # warmup
    print(f"target={BASE} model={MODEL}")
    rows = []
    for name, (prompt, mt) in CASES.items():
        tt, gg = [], []
        for i in range(args.runs):
            p = prompt if prompt else (
                f"[{args.tag}-{i}] Operations notes follow. Read fully.\n"
                + filler(6000, f"{args.tag}-{i}")
                + "\nIn one short sentence: what kind of text is above?")
            r = stream_chat(p, mt)
            tt.append(r["ttft"]); gg.append(r["gen_tps"])
            print(f"  {name} run{i+1}: ttft={r['ttft']}s gen={r['gen_tps']} t/s ({r['chunks']} chunks)", flush=True)
        rows.append((name, statistics.median(tt), statistics.median(gg)))
    print(f"\n=== {args.tag} ===")
    print("| Test | median TTFT | median decode t/s |")
    print("|---|---:|---:|")
    for name, t, g in rows:
        print(f"| {name} | {t}s | {g} |")

if __name__ == "__main__":
    main()
