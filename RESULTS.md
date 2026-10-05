# Results at a glance — miaai35-tune

Visitor-first numbers. Full method and the lab log: [`REPORT.md`](REPORT.md).
Hardware: NVIDIA DGX Spark (GB10, unified memory). Model: Qwen3.6-35B-A3B UD-Q8_K_XL via llama.cpp.

## Primary coding decode, 9 July 2026

Quote this number. It is copied from a committed harness file.

| | |
|---|---|
| **Coding decode** | **35.80 tok/s** |
| What that means | Generated tokens / generation time, not prefill |
| Conditions | ORIGINAL profile, thinking off, clean restart, speculative decode off |
| Source | [`results/bench-original-rerun-think-off-20260709-203311.json`](results/bench-original-rerun-think-off-20260709-203311.json) — `results[]` where `test` is `coding`, field `tokens_per_sec` |
| Same run | short 38.23 · reasoning 35.29 · long context 35.45 tok/s |
| Coding quality | 9/10 on that file |
| Short TTFT | 0.26 s on the coding item · 0.41 s on the short item |
| Long prompt TTFT | 7.56 s at about 9.5k tokens |

The same file is the ~35–38 tok/s band. That is sustained chat speed on this setup.

Biggest interactive win on the day: client `enable_thinking=false`.

## Other figures, kept separate

| Note | Number | Why it is not the headline |
|---|---|---|
| Q8 chat band, 9 July 2026 | **~35–38 tok/s** | The same run, rounded. |
| Later Q8 with speculative decode (PASS18, 10 July 2026) | coding **68.69 tok/s** | [`results/bench-pass18-speed-20260710-084244.json`](results/bench-pass18-speed-20260710-084244.json). Highest coding decode that has a saved JSON file. Speculative decode is on, so it is a different setup. |
| Live note in the report, 11 July 2026 | coding **169.4 t/s** | [`REPORT.md`](REPORT.md) §16, NVFP4 v8 exclusive confirm (refactor 264.2 on the same line). No committed `results/*.json` contains 169.4. Do not quote it as this repo's measured throughput. |

## How to read a row in REPORT.md

| Column | Meaning |
|---|---|
| tok/s | Generated tokens / generation time (not prefill) |
| TTFT | Time to first token |
| VRAM / RAM | Process footprint during that run |
| Quality | Rubric score for that prompt family |
| Stability | pass = no crash/unload in that test |

Use **clean-restart** rows when two numbers disagree. First warm run can look faster (~42–44 tok/s) because weights are already paged.

## Reproduce

```bash
./setup.sh
# llama-server already up:
./.venv/bin/python bench_v5.py --base http://127.0.0.1:8889 --tag local
```

Weights are not in git. Point the bench at your own GGUF + server.
