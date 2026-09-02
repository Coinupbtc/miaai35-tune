# Results at a glance — miaai35-tune

Visitor-first numbers. Full method, raw JSON, and caveats: [`REPORT.md`](REPORT.md).  
Hardware: NVIDIA DGX Spark (GB10, unified memory). Model: Qwen3.6-35B-A3B UD-Q8_K_XL via llama.cpp.

**One primary metric.** Anywhere this repo needs a single tok/s number, use the coding-decode value below. It is copied from a committed harness JSON, not a live note.

## Primary (thinking off, clean ORIGINAL restart)

| What you care about | Result | Source |
|---|---|---|
| **Primary — coding decode** | **35.80 tok/s** | [`results/bench-original-rerun-think-off-20260709-203311.json`](results/bench-original-rerun-think-off-20260709-203311.json) field `tests[coding].tokens_per_sec` (`35.8`; llama.cpp `timings.predicted_per_second` = 35.8028…) |
| Same-run suite | short 38.23 / reasoning 35.29 / long 35.45 tok/s | same file, `tokens_per_sec` |
| Short time-to-first-token | **0.26 s** coding / **0.41 s** short | same file, `ttft_s` |
| Long prompt TTFT (~9.5k tok) | **7.56 s** | same file, `long_context.ttft_s` |
| Coding suite | **9/10** | same file, `quality_score` |
| VRAM (BALANCED) | **39510 MiB** | [`results/bench-balanced-final-think-off-20260709-204018.json`](results/bench-balanced-final-think-off-20260709-204018.json) `tests[coding].vram_mib` |

Conditions for the primary: ORIGINAL profile, `enable_thinking=false`, clean restart, UD-Q8_K_XL, speculative decode off. That is the canonical baseline named in [`REPORT.md`](REPORT.md) §3–4.

Biggest interactive win: client `enable_thinking=false` (wall-clock, not raw tok/s).

## Secondary (different conditions — do not mix into the headline)

| Note | Number | Why it is secondary |
|---|---|---|
| First warm run (not a clean restart) | coding 42.80 / short 44.39 tok/s | [`results/bench-baseline-think-off-20260709-202553.json`](results/bench-baseline-think-off-20260709-202553.json) — weights already paged; REPORT says use the clean numbers |
| Later Q8 + MTP + ngram (PASS18) | coding **68.69 tok/s** | [`results/bench-pass18-speed-20260710-084244.json`](results/bench-pass18-speed-20260710-084244.json) — speculative decode on; highest *sourced* coding decode in this repo |
| Unsourced live note “169.4 t/s” | **not a headline** | Appears only in [`REPORT.md`](REPORT.md) §16 as a v8 NVFP4 live exclusive confirm. **No committed `results/*.json` contains 169 or 169.4.** Do not quote it as measured throughput from this repo. |

## How to read a row in REPORT.md

| Column | Meaning |
|---|---|
| tok/s | Generated tokens / generation time (not prefill) |
| TTFT | Time to first token |
| VRAM / RAM | Process footprint during that run |
| Quality | Rubric score for that prompt family |
| Stability | pass = no crash/unload in that test |

Use **clean-restart** rows when two numbers disagree. Cite the JSON path, not a range, when you need one number.

## Reproduce

```bash
./setup.sh
# llama-server already up:
./.venv/bin/python bench_v5.py --base http://127.0.0.1:8889 --tag local
```

Weights are not in git. Point the bench at your own GGUF + server.
