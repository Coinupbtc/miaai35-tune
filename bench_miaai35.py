#!/usr/bin/env python3
"""Measured benchmark suite for MiaAI-Lab Qwen3.6-35B-A3B on llama-server.

Reports only observed numbers (never invents). Streaming for TTFT.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:8889"
MODEL_PATH = (
    "$HOME/models/dgx_bundle/qwen3.6-35b-a3b-ud/"
    "Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf"
)

# Fixed prompts for repeatable before/after. Temperature 0.1 for stability.
PROMPTS: dict[str, dict[str, Any]] = {
    "short": {
        "label": "Short prompt",
        # thinking models need headroom for CoT before final answer
        "max_tokens": 1024,
        "max_tokens_no_think": 128,
        "content": (
            "Reply in exactly one sentence: what is 17 * 24? "
            "Then name the capital of Japan."
        ),
        "quality_checks": [
            (r"\b408\b", "correct product 408"),
            (r"Tokyo|東京", "capital Tokyo"),
        ],
    },
    "coding": {
        "label": "Coding prompt",
        "max_tokens": 2048,
        "max_tokens_no_think": 700,
        "content": (
            "Write a Python function `def merge_intervals(intervals: list[list[int]]) "
            "-> list[list[int]]:` that merges overlapping intervals. "
            "Include type hints, a docstring, and 3 assert-based tests. "
            "No markdown fences outside the code block. Prefer clear O(n log n) code."
        ),
        "quality_checks": [
            (r"def\s+merge_intervals\s*\(", "defines merge_intervals"),
            (r"sort", "sorts intervals"),
            (r"assert", "includes asserts"),
            (r"list\[list\[int\]\]|List\[List\[int\]\]", "type hints"),
        ],
    },
    "reasoning": {
        "label": "Reasoning prompt",
        "max_tokens": 2048,
        "max_tokens_no_think": 512,
        "content": (
            "A farmer has chickens and rabbits. Together they have 35 heads and "
            "94 legs. How many chickens and how many rabbits? "
            "Show equations, solve step by step, end with: "
            "CHICKENS=<n> RABBITS=<m>"
        ),
        "quality_checks": [
            (r"CHICKENS\s*=\s*23|23\s*chickens", "23 chickens"),
            (r"RABBITS\s*=\s*12|12\s*rabbits", "12 rabbits"),
            (r"2c|2\s*\*\s*c|c\s*\+\s*r|heads|legs", "uses equations"),
        ],
    },
    "long_context": {
        "label": "Long-context prompt",
        "max_tokens": 1024,
        "max_tokens_no_think": 256,
        "content": None,  # filled at runtime
        "quality_checks": [
            (r"ALPHA-TOKEN-7F3C", "recalls ALPHA token"),
            (r"BETA-TOKEN-9K2M", "recalls BETA token"),
            (r"42|forty.?two", "recalls number 42"),
        ],
    },
}


def long_context_body() -> str:
    filler = (
        "This is padding paragraph about local inference on unified memory. "
        "KV cache size grows with context length; MoE models route experts per token. "
        "Benchmark noise comes from other GPU processes and thermal/power limits. "
    ) * 120
    return (
        "You will be given a long document. Ignore most of it. "
        "At the start: SECRET_A=ALPHA-TOKEN-7F3C. "
        "In the middle marker: SECRET_B=BETA-TOKEN-9K2M and ANSWER_N=42. "
        "Document:\n"
        f"{filler}\n"
        "MIDDLE_MARKER: SECRET_B=BETA-TOKEN-9K2M ANSWER_N=42\n"
        f"{filler}\n"
        "END. Report only: A=<SECRET_A> B=<SECRET_B> N=<ANSWER_N> in one line."
    )


def mem_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        free = subprocess.check_output(["free", "-b"], text=True)
        for line in free.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                out["ram_total_gb"] = round(int(parts[1]) / 1e9, 2)
                out["ram_used_gb"] = round(int(parts[2]) / 1e9, 2)
                out["ram_available_gb"] = round(int(parts[6]) / 1e9, 2)
    except Exception as e:  # noqa: BLE001
        out["ram_error"] = str(e)
    try:
        smi = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        apps = []
        total_mib = 0
        for line in smi.strip().splitlines():
            if not line.strip():
                continue
            pid, name, mem = [x.strip() for x in line.split(",", 2)]
            try:
                m = int(mem)
            except ValueError:
                m = 0
            total_mib += m
            apps.append({"pid": pid, "name": name, "used_mib": m})
        out["gpu_apps"] = apps
        out["gpu_used_mib_sum"] = total_mib
        # Best-effort process RSS for llama-server
        for a in apps:
            if "llama-server" in a["name"]:
                out["llama_gpu_mib"] = a["used_mib"]
    except Exception as e:  # noqa: BLE001
        out["gpu_error"] = str(e)
    try:
        util = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        parts = [p.strip() for p in util.split(",")]
        if len(parts) >= 2:
            out["gpu_util_pct"] = parts[0]
            out["gpu_mem_util_pct"] = parts[1]
    except Exception:
        pass
    try:
        # RSS of llama-server
        ps = subprocess.check_output(
            ["ps", "-C", "llama-server", "-o", "rss=", "--no-headers"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if ps:
            # sum if multiple
            rss_kb = sum(int(x) for x in ps.split() if x.isdigit())
            out["llama_rss_gb"] = round(rss_kb / 1e6, 2)
    except Exception:
        pass
    # CPU overall
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        fields = [int(x) for x in line.split()[1:]]
        idle = fields[3] + fields[4]
        total = sum(fields)
        out["_cpu_idle"] = idle
        out["_cpu_total"] = total
    except Exception:
        pass
    return out


def cpu_pct_between(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    if "_cpu_idle" not in a or "_cpu_idle" not in b:
        return None
    di = b["_cpu_idle"] - a["_cpu_idle"]
    dt = b["_cpu_total"] - a["_cpu_total"]
    if dt <= 0:
        return None
    return round(100.0 * (1.0 - di / dt), 1)


def quality_score(text: str, checks: list[tuple[str, str]]) -> tuple[float, list[str]]:
    """Heuristic 0-10 based on required patterns; not LLM-as-judge."""
    if not text or not text.strip():
        return 0.0, ["empty response"]
    hits = []
    misses = []
    for pat, name in checks:
        if re.search(pat, text, re.I | re.S):
            hits.append(name)
        else:
            misses.append(name)
    n = len(checks)
    if n == 0:
        return 8.0, ["no checks"]
    ratio = len(hits) / n
    # Map ratio to 0-10 with partial credit for length/structure
    base = ratio * 10.0
    if len(text.strip()) < 20 and ratio < 1:
        base = min(base, 4.0)
    # Cap: all checks -> 9-10 range if coherent
    if ratio == 1.0:
        score = 9.0 if len(text) > 40 else 8.5
    elif ratio >= 0.75:
        score = 8.0
    elif ratio >= 0.5:
        score = 6.0
    elif ratio >= 0.25:
        score = 4.0
    else:
        score = 2.0 if text.strip() else 0.0
    notes = [f"pass:{h}" for h in hits] + [f"miss:{m}" for m in misses]
    return score, notes


def stream_chat(
    base: str,
    model: str,
    content: str,
    max_tokens: int,
    temperature: float,
    enable_thinking: bool = True,
    timeout: float = 600.0,
) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/v1/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {
            "enable_thinking": enable_thinking,
            "preserve_thinking": enable_thinking,
        },
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    ttft = None
    content_chunks: list[str] = []
    reasoning_chunks: list[str] = []
    usage: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    finish_reason = None
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if "timings" in obj:
                    timings = obj["timings"]
                if "usage" in obj and obj["usage"]:
                    usage = obj["usage"]
                choices = obj.get("choices") or []
                if not choices:
                    continue
                ch0 = choices[0]
                delta = ch0.get("delta") or {}
                piece = delta.get("content") or ""
                reasoning = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or ""
                )
                if piece or reasoning:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    if piece:
                        content_chunks.append(piece)
                    if reasoning:
                        reasoning_chunks.append(reasoning)
                if ch0.get("finish_reason"):
                    finish_reason = ch0.get("finish_reason")
                msg = ch0.get("message") or {}
                if msg.get("content") and not content_chunks:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    content_chunks.append(msg["content"])
                if msg.get("reasoning_content") and not reasoning_chunks:
                    reasoning_chunks.append(msg["reasoning_content"])
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t1 = time.perf_counter()
    text = "".join(content_chunks)
    reasoning_text = "".join(reasoning_chunks)

    # Non-stream fallback if stream failed
    if err or (not text and not reasoning_text and not usage):
        body["stream"] = False
        body.pop("stream_options", None)
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                obj = json.loads(resp.read().decode())
            t1 = time.perf_counter()
            ttft = t1 - t0  # non-stream: TTFT ~= total (conservative)
            choices = obj.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = msg.get("content") or ""
                reasoning_text = msg.get("reasoning_content") or ""
                finish_reason = choices[0].get("finish_reason")
            usage = obj.get("usage") or {}
            timings = obj.get("timings") or timings
            err = None if (text or reasoning_text) else err
        except Exception as e2:  # noqa: BLE001
            err = f"{err}; fallback {type(e2).__name__}: {e2}"
            t1 = time.perf_counter()

    # Score final answer: prefer content; else reasoning (thinking models)
    answer_for_quality = text.strip() if text.strip() else reasoning_text

    total = t1 - t0
    pred_n = None
    pred_ms = None
    prompt_n = None
    prompt_ms = None
    if timings:
        pred_n = timings.get("predicted_n") or timings.get("n_predicted")
        pred_ms = timings.get("predicted_ms")
        prompt_n = timings.get("prompt_n")
        prompt_ms = timings.get("prompt_ms")
    comp = usage.get("completion_tokens")
    prompt_tokens = usage.get("prompt_tokens")
    if pred_n is None:
        pred_n = comp
    if prompt_n is None:
        prompt_n = prompt_tokens

    tps = None
    if pred_n and pred_ms and float(pred_ms) > 0:
        tps = float(pred_n) / (float(pred_ms) / 1000.0)
    elif pred_n and total > 0 and ttft is not None and total > ttft:
        gen_time = total - ttft
        if gen_time > 0:
            tps = float(pred_n) / gen_time
    elif pred_n and total > 0:
        tps = float(pred_n) / total

    prompt_tps = None
    if prompt_n and prompt_ms and float(prompt_ms) > 0:
        prompt_tps = float(prompt_n) / (float(prompt_ms) / 1000.0)

    return {
        "text": text,
        "reasoning_text": reasoning_text,
        "answer_for_quality": answer_for_quality,
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "total_s": round(total, 3),
        "completion_tokens": pred_n,
        "prompt_tokens": prompt_n,
        "tokens_per_sec": round(tps, 2) if tps is not None else None,
        "prompt_tokens_per_sec": round(prompt_tps, 2) if prompt_tps is not None else None,
        "timings": timings,
        "usage": usage,
        "finish_reason": finish_reason,
        "error": err,
        "enable_thinking": enable_thinking,
    }


def health(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def run_suite(
    base: str,
    model: str,
    temperature: float,
    labels: list[str],
    tag: str,
    out_dir: Path,
    enable_thinking: bool = True,
) -> dict[str, Any]:
    if not health(base):
        raise SystemExit(f"health check failed for {base}")

    PROMPTS["long_context"]["content"] = long_context_body()
    mem0 = mem_snapshot()
    results = []
    for key in labels:
        spec = PROMPTS[key]
        max_tok = (
            int(spec.get("max_tokens", 512))
            if enable_thinking
            else int(spec.get("max_tokens_no_think", spec.get("max_tokens", 512)))
        )
        print(
            f"\n=== {spec['label']} ({key}) think={enable_thinking} max_tok={max_tok} ===",
            flush=True,
        )
        m_before = mem_snapshot()
        r = stream_chat(
            base,
            model,
            spec["content"],
            max_tok,
            temperature,
            enable_thinking=enable_thinking,
        )
        m_after = mem_snapshot()
        cpu = cpu_pct_between(m_before, m_after)
        score, notes = quality_score(
            r.get("answer_for_quality") or "", spec["quality_checks"]
        )
        # Content empty but reasoning has answer still counts if score ok
        stability = "fail" if r["error"] or (score == 0 and not r.get("answer_for_quality")) else "pass"
        if r["error"]:
            stability = "fail"
        row = {
            "test": key,
            "label": spec["label"],
            "enable_thinking": enable_thinking,
            "tokens_per_sec": r["tokens_per_sec"],
            "ttft_s": r["ttft_s"],
            "total_s": r["total_s"],
            "completion_tokens": r["completion_tokens"],
            "prompt_tokens": r["prompt_tokens"],
            "prompt_tokens_per_sec": r["prompt_tokens_per_sec"],
            "vram_mib": m_after.get("llama_gpu_mib") or m_after.get("gpu_used_mib_sum"),
            "ram_used_gb": m_after.get("ram_used_gb"),
            "llama_rss_gb": m_after.get("llama_rss_gb"),
            "gpu_util_pct": m_after.get("gpu_util_pct"),
            "cpu_use_pct": cpu,
            "quality_score": score,
            "quality_notes": notes,
            "stability": stability,
            "finish_reason": r["finish_reason"],
            "error": r["error"],
            "text_preview": (r["text"] or "")[:500],
            "reasoning_preview": (r.get("reasoning_text") or "")[:300],
            "timings": r["timings"],
        }
        results.append(row)
        print(
            f"  tps={row['tokens_per_sec']} ttft={row['ttft_s']}s total={row['total_s']}s "
            f"q={score}/10 stab={stability} toks={row['completion_tokens']}",
            flush=True,
        )
        if r["error"]:
            print(f"  ERROR: {r['error']}", flush=True)
        time.sleep(1.0)

    mem1 = mem_snapshot()
    report = {
        "tag": tag,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "model": model,
        "temperature": temperature,
        "enable_thinking": enable_thinking,
        "mem_before": {k: v for k, v in mem0.items() if not k.startswith("_")},
        "mem_after": {k: v for k, v in mem1.items() if not k.startswith("_")},
        "results": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"bench-{tag}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {path}", flush=True)

    print(
        "\n| Test | Tokens/sec | TTFT | Total time | VRAM | RAM | GPU use | CPU use | Quality | Stability |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in results:
        print(
            f"| {row['label']} | {row['tokens_per_sec'] if row['tokens_per_sec'] is not None else '—'} | "
            f"{row['ttft_s'] if row['ttft_s'] is not None else '—'}s | {row['total_s']}s | "
            f"{row['vram_mib']} MiB | {row['ram_used_gb']} GB | {row['gpu_util_pct']}% | "
            f"{row['cpu_use_pct'] if row['cpu_use_pct'] is not None else '—'}% | "
            f"{row['quality_score']}/10 | {row['stability']} |"
        )
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("MIA_BASE", DEFAULT_BASE))
    ap.add_argument("--model", default=os.environ.get("MIA_MODEL", MODEL_PATH))
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument(
        "--tests",
        default="short,coding,reasoning,long_context",
        help="comma-separated test keys",
    )
    ap.add_argument("--tag", default="baseline")
    ap.add_argument(
        "--out-dir",
        default="$HOME/models/dgx_bundle/miaai35-tune/results",
    )
    ap.add_argument(
        "--thinking",
        choices=["on", "off"],
        default="on",
        help="enable_thinking in chat_template_kwargs",
    )
    args = ap.parse_args()
    labels = [x.strip() for x in args.tests.split(",") if x.strip()]
    run_suite(
        args.base,
        args.model,
        args.temperature,
        labels,
        args.tag,
        Path(args.out_dir),
        enable_thinking=(args.thinking == "on"),
    )


if __name__ == "__main__":
    main()
