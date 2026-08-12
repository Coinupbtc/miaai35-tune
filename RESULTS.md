# Results at a glance — miaai35-tune

Visitor-first numbers. Full method, raw JSON, and caveats: [`REPORT.md`](REPORT.md).  
Hardware: NVIDIA DGX Spark (GB10, unified memory). Model: Qwen3.6-35B-A3B UD-Q8_K_XL via llama.cpp. **Measured 2026-07-09, not estimates.**

## Headline (thinking off, clean restart)

| What you care about | Result | Why it matters |
|---|---|---|
| Sustained decode | **~35–38 tok/s** | Interactive chat speed on this box |
| Short time-to-first-token | **~0.25–0.5 s** | Snappy start |
| Long prompt TTFT (~9.5k tok) | **~7–8 s** | Prefill cost is real |
| Coding suite | **~9/10** | Quality held while tuning flags |
| VRAM (BALANCED) | **~39.5 GB** | Fits with headroom on 121 GB unified |

Biggest interactive win: client `enable_thinking=false`.

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
