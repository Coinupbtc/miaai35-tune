# Results at a glance — miaai35-tune

This repo is the **single public hero** for Coinupbtc throughput. Homepage and profile copy this block — nothing else.

Visitor-first numbers. Lab log: [`REPORT.md`](REPORT.md).  
Hardware: NVIDIA DGX Spark (GB10, unified memory). Model: Qwen3.6-35B-A3B UD-Q8_K_XL via llama.cpp.

## Public hero (copy onto homepage / profile)

| | |
|---|---|
| **Number** | **35.80 tok/s** |
| Same-file band | 35.29–38.23 tok/s (**~35–38**) |
| Meaning | Coding-prompt decode: generated tokens / generation time (not prefill) |
| File | [`results/bench-original-rerun-think-off-20260709-203311.json`](results/bench-original-rerun-think-off-20260709-203311.json) |
| Field | `results[]` entry `"test": "coding"` → `tokens_per_sec` = `35.8` (llama.cpp `timings.predicted_per_second` = 35.8028…) |
| Conditions | ORIGINAL profile, thinking off, clean restart, UD-Q8_K_XL, speculative decode off |
| **Do not use** | **169 t/s** — not in any committed `results/*.json` |

`README.md` repeats this number. `REPORT.md` is the campaign log, not the public source of truth.

## Same JSON, other rows (not the hero)

| What you care about | Result | Field in the file above |
|---|---|---|
| Short / reasoning / long decode | 38.23 / 35.29 / 35.45 tok/s | `"test": "short"` / `"reasoning"` / `"long_context"` → `tokens_per_sec` |
| Short TTFT | **0.26 s** coding / **0.41 s** short | `ttft_s` |
| Long prompt TTFT (~9.5k tok) | **7.56 s** | `"test": "long_context"` → `ttft_s` |
| Coding suite | **9/10** | `quality_score` |
| VRAM (BALANCED) | **39510 MiB** | [`results/bench-balanced-final-think-off-20260709-204018.json`](results/bench-balanced-final-think-off-20260709-204018.json) `"test": "coding"` → `vram_mib` |

Biggest interactive win: client `enable_thinking=false` (wall-clock, not raw tok/s).

## Secondary (different conditions — do not mix into the hero)

| Note | Number | Why it is secondary |
|---|---|---|
| First warm run (not a clean restart) | coding 42.80 / short 44.39 tok/s | [`results/bench-baseline-think-off-20260709-202553.json`](results/bench-baseline-think-off-20260709-202553.json) — weights already paged |
| Later Q8 + MTP + ngram (PASS18) | coding **68.69 tok/s** | [`results/bench-pass18-speed-20260710-084244.json`](results/bench-pass18-speed-20260710-084244.json) — speculative decode on |
| Unsourced live note “169.4 t/s” | **deleted as a public figure** | REPORT §16 campaign notebook only. **No committed JSON contains 169 or 169.4.** |

## How to read a row in REPORT.md

| Column | Meaning |
|---|---|
| tok/s | Generated tokens / generation time (not prefill) |
| TTFT | Time to first token |
| VRAM / RAM | Process footprint during that run |
| Quality | Rubric score for that prompt family |
| Stability | pass = no crash/unload in that test |

When two numbers disagree, the public hero in the table at the top of this file wins.

## Reproduce

```bash
./setup.sh
# llama-server already up:
./.venv/bin/python bench_v5.py --base http://127.0.0.1:8889 --tag local
```

Weights are not in git. Point the bench at your own GGUF + server.
