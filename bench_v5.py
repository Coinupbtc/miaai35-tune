#!/usr/bin/env python3
"""v5 rigorous personalized eval for llama-miaai35 (:8889).

Built from a realistic local-ops workload (agent sessions + cron-style digests):
  A. ops-digest QA — faithfulness to injected context (exact match)
  B. hallucination trap — must acknowledge absent info, not invent status
  C. completeness enumeration — recall AND precision over failing items
  D. Telegram brief — strict format compliance (MAX lines, bullets only)
  E. coding — generated code is EXECUTED against unit tests
  F. multi-step reasoning — exact numeric/boolean answers
  G. tool calling — valid OpenAI tool_call with correct args

Every check is objective. Score = weighted pass fraction (0-100), with real
headroom — unlike the saturated 9/10 harness. Also reports per-category gen t/s.

Usage: python3 bench_v5.py --tag v4-baseline [--thinking on|off]
"""
import argparse, datetime, json, pathlib, re, statistics, subprocess, tempfile, urllib.request

import os
BASE = os.environ.get("MIA_BASE", "http://127.0.0.1:8889")

DIGEST = """DGX DAILY DIGEST 2026-07-10 06:00
services: llama-miaai35 active | comfyui active | vllm-nvfp4 inactive (by design) |
stl-sandbox active | agent-gateway-main active | agent-gateway-light FAILED (exit 2, 05:41) |
ollama active
backups: restic OK 03:12 | backup-mirror FAILED 04:20 (ssh timeout) | edge-node DEGRADED (bridge down)
resources: disk 21% used | RAM 61/121 GB | swap 1/15 GB
trading: paper-book 3 positions open, cycle OK 04:00 | lane-scan scan OK, 42 matches, 2 flagged for review
cron: sleep-research-scanner exit 2 at 05:00 | vault-lint OK 09:00 (prev day)"""

def chat(messages, max_tokens=700, thinking=False, tools=None, temperature=0.1):
    import time as _time
    body = {"model": os.environ.get("MIA_MODEL", "m"), "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": thinking}}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(BASE + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    _t0 = _time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    _wall = _time.time() - _t0
    t = d.get("timings", {})
    msg = d["choices"][0]["message"]
    gen_tps = t.get("predicted_per_second")
    gen_n = t.get("predicted_n") or d.get("usage", {}).get("completion_tokens")
    if gen_tps is None and gen_n and _wall > 0:
        gen_tps = gen_n / _wall  # includes PP time; lower bound (vLLM has no timings field)
    return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls"),
            "gen_tps": gen_tps, "gen_n": gen_n}

def run_python(code, test_code):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code + "\n\n" + test_code + "\nprint('ALL_TESTS_PASS')\n")
        path = f.name
    try:
        p = subprocess.run(["python3", path], capture_output=True, text=True, timeout=15)
        return "ALL_TESTS_PASS" in p.stdout, (p.stderr or p.stdout)[-300:]
    except Exception as e:
        return False, str(e)[:300]
    finally:
        pathlib.Path(path).unlink(missing_ok=True)

def extract_code(text):
    m = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return m[-1] if m else text

CHECKS = []
def check(name, cat, passed, detail=""):
    CHECKS.append({"name": name, "cat": cat, "pass": bool(passed), "detail": str(detail)[:200]})
    print(f"  [{'PASS' if passed else 'FAIL'}] {cat}/{name} {detail if not passed else ''}", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--thinking", choices=["on", "off"], default="off")
    args = ap.parse_args()
    think = args.thinking == "on"
    tps_by_cat = {}

    def record(cat, r):
        tps_by_cat.setdefault(cat, []).append(r["gen_tps"] or 0)

    chat([{"role": "user", "content": "Say OK."}], 8)  # warmup

    # --- A. faithfulness QA (exact answers from digest) ---
    qa = [
        ("Which gateway service failed?", lambda s: "light" in s.lower()),
        ("At what time (HH:MM) did the backup-mirror backup fail?", lambda s: "04:20" in s),
        ("How many lane-scan matches are flagged for review?",
         lambda s: re.search(r"\b(2|two)\b", s.lower()) and not re.search(r"\b42 flagged", s)),
        ("What is the swap usage in GB?", lambda s: bool(re.search(r"(^|[^0-9.])1\s*(gb|gib|/\s*15|of\s*15|out of\s*15)", s.lower()))),
    ]
    for i, (q, ok) in enumerate(qa):
        r = chat([{"role": "system", "content": "Answer strictly from the provided digest. Be concise."},
                  {"role": "user", "content": DIGEST + "\n\nQuestion: " + q}], 120, think)
        record("A_faithfulness", r)
        check(f"qa{i+1}", "A_faithfulness", ok(r["content"]), r["content"][:80])

    # --- B. hallucination trap: asks about something NOT in the digest ---
    r = chat([{"role": "system", "content": "Answer strictly from the provided digest. Be concise."},
              {"role": "user", "content": DIGEST + "\n\nQuestion: What is the current status of the mistral-download service?"}],
             120, think)
    record("B_trap", r)
    s = r["content"].lower()
    admits_absence = bool(re.search(r"(no|not|doesn't|does not|isn't|is not)[^.]{0,50}"
                                    r"(list|mention|includ|present|appear|in the digest|information|found|such)", s))
    invents = re.search(r"mistral[^.]{0,40}\b(is|:)\s*(active|running|failed|inactive|degraded)", s) and not admits_absence
    check("absent-service", "B_trap", admits_absence and not invents, r["content"][:100])

    # trap 2: cross-attribution confusion (mirrors real logged complaint:
    # user had to correct an agent that mixed up lane-scan with another system)
    r = chat([{"role": "system", "content": "Answer strictly from the provided digest. Be concise."},
              {"role": "user", "content": DIGEST + "\n\nQuestion: How many open trading positions does lane-scan currently have?"}],
             150, think)
    record("B_trap", r)
    s = r["content"].lower()
    says_none = bool(re.search(r"(no open|none|zero|0 open|do(es)?n?'?t (have|track|hold|state|say|report|mention|show|list|indicate)|does not (have|track|hold|state|say|report|mention|show|list|indicate)|not (a|the) trading|no positions|isn't .*positions)", s))
    steals_crypto = bool(re.search(r"\b3\b[^.]{0,30}position", s)) and not says_none
    check("no-cross-attribution", "B_trap", says_none and not steals_crypto, r["content"][:100])

    # trap 3: false premise — asks when a service failed that actually succeeded
    r = chat([{"role": "system", "content": "Answer strictly from the provided digest. Be concise."},
              {"role": "user", "content": DIGEST + "\n\nQuestion: At what time did vault-lint fail?"}],
             150, think)
    record("B_trap", r)
    s = r["content"].lower()
    rejects_premise = bool(re.search(r"(did not fail|didn't fail|not fail|no fail|was ok|is ok|ran ok|\bok\b|passed|succeed)", s))
    fabricates = bool(re.search(r"fail(ed)?\s*(at|:)?\s*\d{1,2}:\d{2}", s)) and not rejects_premise
    check("false-premise", "B_trap", rejects_premise and not fabricates, r["content"][:100])

    # --- C. completeness enumeration ---
    r = chat([{"role": "system", "content": "Answer strictly from the provided digest."},
              {"role": "user", "content": DIGEST + "\n\nList ALL items that are failing, degraded, or exited nonzero. Complete list, one per line, nothing else."}],
             250, think)
    record("C_enumeration", r)
    s = r["content"].lower()
    expected = {"gateway-light": "light" in s, "backup-mirror": "backup-mirror" in s or "backup mirror" in s,
                "edge-node": "edge-node" in s, "sleep-research": "sleep-research" in s or "sleep research" in s}
    false_pos = [w for w in ["llama-miaai35", "comfyui", "restic", "vault-lint", "stl-sandbox", "ollama"]
                 if re.search(rf"^[^a-z]*{re.escape(w)}", s, re.M)]
    recall = sum(expected.values())
    check("recall-4of4", "C_enumeration", recall == 4, f"found {recall}/4: {expected}")
    check("no-false-positives", "C_enumeration", not false_pos, f"wrongly listed: {false_pos}")

    # --- D. Telegram brief format ---
    r = chat([{"role": "user", "content": DIGEST + "\n\nCompose the Morning Operator Brief for Telegram. MAX 14 lines total. Bullet format only (every line starts with '- '). No preamble, no closing line."}],
             400, think)
    record("D_brief", r)
    lines = [l for l in r["content"].strip().splitlines() if l.strip()]
    bullets = [l for l in lines if l.strip().startswith(("-", "•", "*"))]
    check("max-14-lines", "D_brief", 0 < len(lines) <= 14, f"{len(lines)} lines")
    check("all-bullets", "D_brief", len(bullets) == len(lines), f"{len(bullets)}/{len(lines)} bulleted")
    check("mentions-failures", "D_brief", "light" in r["content"].lower() and "backup-mirror" in r["content"].lower(),
          "brief must surface the two failures")

    # --- E. coding, EXECUTED ---
    coding = [
        ("parse_uptime",
         "Write a Python function parse_uptime(s) that converts strings like '3d 4h 12m', '45m', '1d 2m' into total seconds (int). Only the function, in one ```python block.",
         "assert parse_uptime('3d 4h 12m')==3*86400+4*3600+12*60\nassert parse_uptime('45m')==2700\nassert parse_uptime('1d 2m')==86520\nassert parse_uptime('2h')==7200"),
        ("dedupe_events",
         "Write a Python function dedupe_events(events) taking a list of dicts with keys 'id' and 'ts' (int). Return a list keeping only the entry with the highest ts for each id, sorted by id ascending. Only the function, in one ```python block.",
         "r=dedupe_events([{'id':'b','ts':2},{'id':'a','ts':5},{'id':'b','ts':9},{'id':'a','ts':1}])\nassert r==[{'id':'a','ts':5},{'id':'b','ts':9}], r"),
        ("next_cron_gap",
         "Write a Python function max_idle_gap(times) taking a sorted list of minutes-of-day integers when jobs run (0-1439), returning the LONGEST gap in minutes between consecutive runs, including the wrap-around from last run to first run next day. Only the function, in one ```python block.",
         "assert max_idle_gap([0,360,720,1080])==360\nassert max_idle_gap([60])==1440\nassert max_idle_gap([100,110,1400])==1290"),
    ]
    for name, prompt, tests in coding:
        r = chat([{"role": "user", "content": prompt}], 800, think)
        record("E_coding", r)
        ok, detail = run_python(extract_code(r["content"]), tests)
        check(name, "E_coding", ok, detail)

    # --- F. reasoning, exact answers ---
    reasoning = [
        ("cron-collision",
         "Job A runs every 4 hours starting at 00:00. Job B runs every 6 hours starting at 01:00. During one day (00:00-23:59), at how many clock times do A and B run at the same moment? Think carefully, then end with 'ANSWER: <number>'.",
         lambda s: re.search(r"answer:\s*0\b", s.lower())),
        ("memory-budget",
         "A machine has 121 GB unified memory. Currently used: model 42.5 GB, comfyui 3.2 GB, system reserve 8 GB. Someone wants to load two more models needing 30 GB weights + 5 GB KV cache EACH. Does it fit? End with 'ANSWER: YES' or 'ANSWER: NO'.",
         lambda s: re.search(r"answer:\s*no\b", s.lower())),
        ("gpu-minutes",
         "An agent makes 25 calls per day. Each call processes 3000 prompt tokens at 1500 tokens/sec and generates 550 tokens at 55 tokens/sec. How many total MINUTES of GPU time per day? End with 'ANSWER: <number>'.",
         lambda s: re.search(r"answer:\s*5(\.0+)?\b", s.lower())),
    ]
    for name, q, ok in reasoning:
        r = chat([{"role": "user", "content": q}], 1400, think)
        record("F_reasoning", r)
        check(name, "F_reasoning", bool(ok(r["content"])), r["content"][-80:])

    # --- G. tool calling ---
    tools = [
        {"type": "function", "function": {"name": "run_command", "description": "Run a shell command",
         "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}},
        {"type": "function", "function": {"name": "send_alert", "description": "Send a Telegram alert to the operator",
         "parameters": {"type": "object", "properties": {"message": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "normal", "high"]}},
                        "required": ["message", "priority"]}}},
    ]
    r = chat([{"role": "user", "content": "Disk usage on / just hit 96%. Alert the operator immediately at the appropriate priority. Use a tool."}],
             300, think, tools=tools)
    record("G_toolcall", r)
    ok_tool = False; detail = "no tool_calls"
    if r["tool_calls"]:
        tc = r["tool_calls"][0]
        try:
            fn = tc["function"]["name"]; fnargs = json.loads(tc["function"]["arguments"])
            ok_tool = fn == "send_alert" and fnargs.get("priority") == "high" and ("96" in fnargs.get("message", "") or "disk" in fnargs.get("message", "").lower())
            detail = f"{fn}({fnargs})"
        except Exception as e:
            detail = f"bad args: {e}"
    check("alert-tool", "G_toolcall", ok_tool, detail)

    # --- score ---
    total = len(CHECKS); passed = sum(c["pass"] for c in CHECKS)
    score = round(100 * passed / total, 1)
    print(f"\n=== {args.tag} (thinking={args.thinking}) ===")
    print(f"QUALITY SCORE: {score}%  ({passed}/{total} objective checks)")
    print("| Category | Passed | median gen t/s |")
    print("|---|---|---:|")
    cats = {}
    for c in CHECKS:
        cats.setdefault(c["cat"], [0, 0]); cats[c["cat"]][1] += 1; cats[c["cat"]][0] += c["pass"]
    for cat, (p, n) in cats.items():
        tps = statistics.median(tps_by_cat.get(cat, [0]))
        print(f"| {cat} | {p}/{n} | {tps:.1f} |")
    all_tps = [x for v in tps_by_cat.values() for x in v if x]
    print(f"overall median gen t/s: {statistics.median(all_tps):.1f}")
    out = pathlib.Path(__file__).parent / "results" / f"v5-{args.tag}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"tag": args.tag, "thinking": args.thinking, "score": score,
                               "checks": CHECKS, "tps_by_cat": tps_by_cat}, indent=2))
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
