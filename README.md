# miaai35-tune

Measured **llama.cpp** tune for **Qwen3.6-35B-A3B** on NVIDIA DGX Spark.

Not a from-scratch train — a flag/profile bakeoff with real tok/s, TTFT, quality, and VRAM numbers.

## At a glance

| | |
|---|---|
| **What it is** | A measured **llama.cpp** flag/profile bakeoff for **Qwen3.6-35B-A3B** on NVIDIA DGX Spark — benches, profiles, and a written report with real tok/s / TTFT / quality / VRAM numbers. |
| **What it’s for** | So you can pick serving settings with **evidence**, not vibes — and reproduce (or challenge) the numbers we got on Spark unified memory. |
| **How to use it** | Read [`REPORT.md`](REPORT.md) with no GPU, or `./setup.sh` then point `bench_v5.py` at any OpenAI-compatible `llama-server`. Weights stay local. For a known-good Spark serve path, see [MiaAI Labs’ Qwen3.6-35B recipe](https://github.com/MiaAI-Lab/Qwen3.6-35B-A3B-UD-Q8_K_XL_DGX-Spark-Recipe). |

## Try it (pick one)

### One command
```bash
git clone https://github.com/Coinupbtc/miaai35-tune.git
cd miaai35-tune && ./setup.sh
```

### Copy-paste
```bash
git clone https://github.com/Coinupbtc/miaai35-tune.git && cd miaai35-tune
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# with a local server already on :8889
./.venv/bin/python bench_v5.py --base http://127.0.0.1:8889 --tag local
```

### Just read the results
Open [`REPORT.md`](REPORT.md) — headline numbers below need no GPU.

## Headline numbers (thinking off)

| Metric | Measured |
|--------|----------|
| Sustained decode | ~35–38 tok/s |
| Coding suite | ~9/10 quality |
| Short TTFT | ~0.25–0.5 s |
| Long TTFT (~9.5k tok) | ~7–8 s |
| VRAM (BALANCED) | ~39.5 GB |

Biggest interactive win: client `enable_thinking=false`.

## Layout

| Path | What |
|------|------|
| `REPORT.md` | Full measured report |
| `profiles/` | llama-server profiles (BALANCED, MAX_SPEED, …) |
| `bench_*.py` / `stress_test.py` | Harnesses |
| `results/` | JSON from real runs |
| `setup.sh` | One-command env setup |

Weights are **not** in this repo (multi-GB). Use your own UD-Q8_K_XL (or similar) GGUF with `llama-server`.

## Acknowledgments

Serving baseline for this tune: [MiaAI Labs’ Qwen3.6-35B UD-Q8_K_XL DGX Spark recipe](https://github.com/MiaAI-Lab/Qwen3.6-35B-A3B-UD-Q8_K_XL_DGX-Spark-Recipe) ([MiaAI-Lab](https://github.com/MiaAI-Lab)). This repo is our measured flag/profile bakeoff on top of that recipe — not a general endorsement, and not related to our other projects.


## License

MIT
