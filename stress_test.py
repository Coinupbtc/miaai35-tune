#!/usr/bin/env python3
"""Stress test suite for MiaAI 35B (measured only)."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import bench_miaai35 as B

BASE = "http://127.0.0.1:8889"
MODEL = B.MODEL_PATH
OUT = Path("$HOME/models/dgx_bundle/miaai35-tune/results")


def one(prompt: str, max_tokens: int, tag: str, think: bool) -> dict:
    m0 = B.mem_snapshot()
    r = B.stream_chat(BASE, MODEL, prompt, max_tokens, 0.1, enable_thinking=think)
    m1 = B.mem_snapshot()
    return {
        "tag": tag,
        "tps": r["tokens_per_sec"],
        "ttft": r["ttft_s"],
        "total": r["total_s"],
        "toks": r["completion_tokens"],
        "error": r["error"],
        "vram": m1.get("llama_gpu_mib"),
        "ram": m1.get("ram_used_gb"),
        "preview": (r.get("answer_for_quality") or "")[:200],
    }


def main() -> None:
    if not B.health(BASE):
        raise SystemExit("health fail")
    rows = []
    mem_start = B.mem_snapshot()

    shorts = [
        "Say OK and the number 7.",
        "Capital of France in one word.",
        "2+2=?",
        "Name a sorting algorithm.",
        "Reply: pong",
    ]
    for i, p in enumerate(shorts, 1):
        print(f"short {i}/5", flush=True)
        rows.append(one(p, 64, f"short_{i}", False))

    codes = [
        "Write a Python fibonacci(n) with type hints. No markdown.",
        "Fix: def add(a,b) return a+b  — correct syntax only.",
        "Write a bash one-liner to count lines in *.log under /tmp.",
    ]
    for i, p in enumerate(codes, 1):
        print(f"coding {i}/3", flush=True)
        rows.append(one(p, 256, f"coding_{i}", False))

    reasons = [
        "If all Bloops are Razzies and all Razzies are Lazzies, are all Bloops Lazzies? Yes/No + 1 sentence.",
        "A bat and ball cost $1.10. Bat costs $1 more than ball. Ball cost?",
        "Three switches one bulb classic: strategy in 4 bullets max.",
    ]
    for i, p in enumerate(reasons, 1):
        print(f"reason {i}/3", flush=True)
        rows.append(one(p, 400, f"reason_{i}", False))

    print("long_context", flush=True)
    rows.append(one(B.long_context_body(), 256, "long", False))

    print("debug", flush=True)
    rows.append(
        one(
            "This code fails: xs = [1,2,3]; print(xs[3]). Explain the bug and fix in 3 lines.",
            256,
            "debug",
            False,
        )
    )

    print("agent_multistep", flush=True)
    rows.append(
        one(
            "You are a local agent. Plan 4 steps to add health checks to a systemd user service "
            "named llama-miaai35, then output STEP1..STEP4 only.",
            400,
            "agent",
            False,
        )
    )

    mem_end = B.mem_snapshot()
    tps_vals = [r["tps"] for r in rows if r["tps"] is not None]
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mem_start": {k: v for k, v in mem_start.items() if not str(k).startswith("_")},
        "mem_end": {k: v for k, v in mem_end.items() if not str(k).startswith("_")},
        "rows": rows,
        "tps_min": min(tps_vals) if tps_vals else None,
        "tps_max": max(tps_vals) if tps_vals else None,
        "tps_avg": round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None,
        "errors": sum(1 for r in rows if r["error"]),
        "vram_delta_mib": (
            (mem_end.get("llama_gpu_mib") or 0) - (mem_start.get("llama_gpu_mib") or 0)
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"stress-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("tps_min", "tps_max", "tps_avg", "errors", "vram_delta_mib")}, indent=2))
    print("wrote", path)
    for r in rows:
        print(f"{r['tag']}: tps={r['tps']} ttft={r['ttft']} total={r['total']} err={r['error']}")


if __name__ == "__main__":
    main()
