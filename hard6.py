#!/usr/bin/env python3
"""6-item hard-reasoning tiebreaker (thinking ON). Exact integer answers, graded from a
final 'ANSWER: <n>' line so grader bugs can't blame the model. Usage:
  MIA_BASE=http://127.0.0.1:8890 python3 hard6.py --tag candidate
Answers verified by hand when written (2026-07-11)."""
import argparse, json, os, re, time, urllib.request

BASE = os.environ.get("MIA_BASE", "http://127.0.0.1:8889")
MODEL = os.environ.get("MIA_MODEL", "m")

ITEMS = [
    ("cron-count", "A cron job fires every 90 minutes, first firing at 00:15. How many times "
     "does it fire between 00:00 and 24:00 the same day (midnight to midnight, exclusive of "
     "the ending midnight)?", 16),
    ("no-bb-strings", "How many strings of length 5 over the alphabet {a, b} contain no two "
     "consecutive b's?", 13),
    ("code-trace", "What does this Python print?\n```python\nx = [1, 2, 3, 4]\ns = 0\n"
     "for i, v in enumerate(x):\n    if i % 2 == 0:\n        s += v * 2\n    else:\n"
     "        s -= v\nprint(s)\n```", 2),
    ("lcm-watchdogs", "Two watchdogs fire every 84 seconds and every 126 seconds. Both fire "
     "together at t=0. At what t in seconds do they next fire together?", 252),
    ("hex-convert", "What is hexadecimal 0x2F3 in decimal?", 755),
    ("makespan", "Five jobs (A, B, C, D, E) each take exactly 20 minutes. You have 2 runners "
     "that each run one job at a time. Job E may only start after BOTH A and B have finished. "
     "What is the minimum total time in minutes to finish all five jobs?", 60),
]

SUFFIX = "\n\nThink carefully, then end your reply with a final line: ANSWER: <integer>"

def ask(prompt):
    body = json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt + SUFFIX}],
        "temperature": 0.1, "max_tokens": 12288,  # thinking alone can exceed 12k on these; 4096 truncated BOTH engines (finish=length, empty content)
        "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": False},
    }).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]["content"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    passed = 0
    for name, prompt, want in ITEMS:
        t0 = time.time()
        out = ask(prompt)
        m = re.findall(r"ANSWER:\s*(-?\d+)", out)
        got = int(m[-1]) if m else None
        ok = got == want
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: want={want} got={got} ({time.time()-t0:.0f}s)")
        if not ok:
            print("    tail:", out[-300:].replace("\n", " | "))
    print(f"\n[{args.tag}] hard6: {passed}/6")

if __name__ == "__main__":
    main()
