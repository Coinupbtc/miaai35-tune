# MiaAI-Lab Qwen3.6-35B — Measured Tune Report

> **Note:** Serving baseline for these measurements was MiaAI Labs’ [Qwen3.6-35B Spark recipe](https://github.com/MiaAI-Lab/Qwen3.6-35B-A3B-UD-Q8_K_XL_DGX-Spark-Recipe). Numbers and profiles below are ours.

**Date:** 2026-07-09  
**Host:** DGX Spark GB10 (aarch64, Ubuntu 24.04)  
**Rule:** numbers below were measured; no estimates.

## Revert to original (always available)

```bash
$HOME/models/dgx_bundle/miaai35-tune/revert-original.sh
# or:
$HOME/models/dgx_bundle/miaai35-tune/apply-profile.sh ORIGINAL
```

Backup of pre-tune unit:
`miaai35-tune/backups/llama-miaai35.service.ORIGINAL-2026-07-09`

---

## 1. System inventory

| Item | Value |
|---|---|
| OS | Ubuntu 24.04.4 LTS, Linux 6.17.0-1026-nvidia aarch64 |
| CPU | 10× Cortex-X925 + 10× Cortex-A725 (20 cores) |
| GPU | NVIDIA GB10 (unified memory with CPU) |
| RAM | 121 GiB total; ~58–64 GiB available during tests |
| Storage | 3.7T NVMe, ~2.8T free |
| Driver | 580.159.03 |
| CUDA | toolkit 13.0 (nvcc present) |
| AI runners | llama-server (CUDA build `~/llama.cpp/build/bin`), Ollama :11434, vLLM unit present but not serving during tests, ComfyUI |
| Live GPU apps (during baseline) | llama-server ~40 GB; ComfyUI ~0.4 GB; python3 ~3.1 GB; gnome-remote-desktop ~0.4 GB |

## 2. Model inventory

| Field | Value |
|---|---|
| Exact name | MiaAI-Lab **Qwen3.6-35B-A3B** UD-Q8_K_XL (MoE ~35B-A3B) |
| File | `$HOME/models/dgx_bundle/downloads/Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf` (36G / 38451182560 bytes) |
| Vision | `mmproj-BF16.gguf` (~862M) |
| Quantization on disk | **UD-Q8_K_XL only** (no Q4/Q5 local) |
| Context (server) | 131072 configured; train n_ctx 262144 |
| Runner | `llama-server` CUDA, systemd `llama-miaai35.service` |
| Endpoint | `http://127.0.0.1:8889/v1` (also `/health`, `/props`, `/slots`) |
| Cold load | ~7–13 s warm restart (weights page-cached); first boot can be longer |
| GPU acceleration | Yes (~39–40.5 GiB process footprint) |
| CPU offload | Not observed (full GPU path) |
| Spec decode / MTP | **Off** — this GGUF has no MTP layers (`SPEC_DECODE=0` by design) |
| Stability | Healthy during suite; no crash/unload in stress test |

---

## 3. Baseline (clean ORIGINAL after restart, think-off)

Canonical baseline tag: `original-rerun-think-off`  
(First warm “baseline-think-off” hit ~42–44 t/s; after clean restart, sustained decode sits ~35–38 t/s. **Use clean numbers.**)

| Test | Tokens/sec | TTFT | Total time | VRAM | RAM | GPU use | CPU use | Quality | Stability |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Short prompt | 38.23 | 0.413s | 0.988s | 40468 MiB | 61.35 GB | 94% | 15.8% | 9.0/10 | pass |
| Coding prompt | 35.80 | 0.260s | 13.387s | 40470 MiB | 61.19 GB | 94% | 18.0% | 9.0/10 | pass |
| Reasoning prompt | 35.29 | 0.262s | 14.772s | 40470 MiB | 61.37 GB | 94% | 18.9% | 9.0/10 | pass |
| Long-context prompt | 35.45 | 7.555s | 8.289s | 40502 MiB | 61.64 GB | 94% | 17.5% | 9.0/10 | pass |

**Thinking ON** (same ORIGINAL, default CoT) — quality still 9/10 but wall-clock much worse:

| Test | Tokens/sec | TTFT | Total | Quality |
|---|---:|---:|---:|---:|
| Short | 21.01 | 0.255s | 46.5s | 9.0 |
| Coding | 20.99 | 0.460s | 98.0s | 9.0 |
| Reasoning | 22.74 | 0.588s | 69.0s | 9.0 |
| Long-context | 27.31 | 2.034s | 21.4s | 9.0 |

Decode slows as the thinking context grows; total time is dominated by CoT tokens.

---

## 4. Optimization passes (coding t/s = primary speed metric)

Baseline coding = **35.80 t/s**, quality **9/10**.

| Change | t/s before | t/s after | % speed | Q before | Q after | Keep or revert |
|---|---:|---:|---:|---:|---:|---|
| `--parallel 1` | 35.80 | 36.02 | +0.6% | 9 | 9 | **revert** (no real speed gain; hurts multi-agent) |
| `--flash-attn on` | 35.80 | 35.52 | −0.8% | 9 | 9 | **keep** (neutral; explicit) |
| fa + KV `q8_0` | 35.80 | 35.12 | −1.9% | 9 | 9 | **keep** (~1 GB VRAM saved, quality held) |
| ctx 65536 + fa | 35.80 | 35.93 | +0.4% | 9 | 9 | optional (minor) |
| no mmproj + fa | 35.80 | 36.13 | +0.9% | 9 | 9 | optional text-only (loses vision) |
| maxspeed stack (32k/p1/kv-q8/no-mmproj) | 35.80 | 35.28 | −1.5% | 9 | 9 | **keep as Max Speed profile** (memory + long TTFT) |
| Client `enable_thinking=false` | wall-clock 13–98s → 0.7–15s | n/a | **huge wall-clock** | 9 | 9 | **keep for daily use** |

**Decision rule outcome:** No server flag delivered ≥10% decode-token speedup on this Q8 MoE + GB10 path. Decode is compute/bandwidth bound ~35–38 t/s. Real wins: **memory headroom**, **long-prompt TTFT**, and especially **disabling thinking for interactive use**.

---

## 5. Three profiles

Apply with:
```bash
~/models/dgx_bundle/miaai35-tune/apply-profile.sh MAX_SPEED   # or BALANCED | MAX_QUALITY | ORIGINAL
```

### A. Max Speed 35B

| Setting | Value |
|---|---|
| Model | Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf |
| Runner | llama-server CUDA |
| Endpoint | `http://127.0.0.1:8889/v1` |
| Quantization | UD-Q8_K_XL (only quant on disk) |
| Context | 32768 |
| Temperature | 0.4 (server default) |
| Top-p | 0.9 |
| Repeat penalty | 1.05 |
| Max output tokens | 256–512 client |
| GPU layers | auto / all |
| Parallel | 1 |
| KV cache | `q8_0` / `q8_0` |
| Flash attention | on |
| Batch / ubatch | 4096 / 1024 |
| mmproj | **off** (text only) |
| Keep-alive | systemd always-on |
| Client | `chat_template_kwargs: {"enable_thinking": false}` |
| Expected tokens/sec | **~35–38** sustained decode |
| Expected quality | **≥9/10** on suite (measured 9) |
| Use for | quick answers, short coding, summaries |

### B. Balanced 35B (recommended default — **currently applied**)

| Setting | Value |
|---|---|
| Model | same Q8_K_XL + mmproj |
| Runner / endpoint | llama-server :8889 |
| Context | **131072** (4 slots) |
| Temperature | 0.6 |
| Top-p | 0.95 |
| Repeat penalty | 1.0 |
| Flash attention | on |
| KV cache | q8_0 / q8_0 |
| GPU footprint | **~39510 MiB** measured |
| Client daily | `enable_thinking: false` |
| Client hard tasks | `enable_thinking: true` + max_tokens ≥ 2048 |
| Expected tokens/sec | **~35–37** |
| Expected quality | **9/10** |
| Use for | daily driver, coding, planning, local agents |

### C. Max Quality 35B

| Setting | Value |
|---|---|
| Model | Q8_K_XL + mmproj |
| Context | 131072 |
| Temperature | 0.6 |
| Top-p | 0.95 |
| Flash attention | on |
| KV | default (fp16/bf16 path) |
| Client | `enable_thinking: true`, max_tokens 2048–4096 |
| Expected tokens/sec | **~21–27** while thinking grows; final answer quality 9 |
| Use for | hard reasoning, architecture, debugging, long agent chains |

Profile units live in `miaai35-tune/profiles/*.service`.

---

## 6. Stress test (BALANCED-class, thinking off)

14 sequential requests (5 short, 3 coding, 3 reasoning, long, debug, agent):

| Metric | Measured |
|---|---|
| Errors | **0** |
| Sustained t/s (coding/reason/long/agent) | **~35–38** |
| Tiny-gen spikes | up to 79 t/s (unreliable; few tokens) |
| VRAM delta start→end | **+36 MiB** (no leak signal) |
| Unload / crash / timeout | **none** |
| API health after | **ok** |

---

## 7. Final recommendation

| Item | Value |
|---|---|
| Best Max Speed profile | `MAX_SPEED` + client thinking **off** |
| Best Balanced profile | `BALANCED` (fa + KV q8 + 128k + mmproj) — **live now** |
| Best Max Quality profile | `MAX_QUALITY` / `ORIGINAL` + client thinking **on** |
| Fastest measured sustained decode | **~38–40 t/s** short/clean; coding **~35–37 t/s** |
| Best quality score | **9/10** (suite ceiling with current checks) |
| Best speed/quality tradeoff | **BALANCED + thinking off** (~35 t/s @ 9/10) |
| Main bottleneck | **Decode compute on Q8 MoE weights** (~28 ms/token); not KV alone |
| Biggest speed improvement | **Client `enable_thinking=false`** (wall-clock, not raw t/s) |
| Quality loss | **None measured** on kept settings (all ≥9/10) |
| Settings to avoid | CPU-only `~/.local/bin/llama-server` (~7 t/s historical); enabling MTP on non-MTP GGUF (aborts load); rapid restart loops (systemd start-limit); expecting ≥10% t/s from flag churn on this quant |
| Recommended default | **BALANCED** |
| When Max Speed | Interactive chat, short coding, when free memory needed for other GPU apps |
| When Max Quality | Architecture / hard bugs / multi-step agent with CoT |
| Remaining risk | Only Q8 quant on disk (Q4 not tested); concurrent ComfyUI/python GPU users; multi-slot agent under load can still contend; thinking-on burns tokens/time |

### Copy-paste: client speed vs quality

```bash
# FAST daily (thinking off)
curl -s http://127.0.0.1:8889/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "$HOME/models/dgx_bundle/qwen3.6-35b-a3b-ud/Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf",
    "messages": [{"role":"user","content":"Write a python hello world"}],
    "temperature": 0.4,
    "max_tokens": 512,
    "chat_template_kwargs": {"enable_thinking": false}
  }'

# QUALITY (thinking on)
curl -s http://127.0.0.1:8889/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "$HOME/models/dgx_bundle/qwen3.6-35b-a3b-ud/Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf",
    "messages": [{"role":"user","content":"Hard design question..."}],
    "temperature": 0.6,
    "max_tokens": 2048,
    "chat_template_kwargs": {"enable_thinking": true, "preserve_thinking": true}
  }'
```

### Re-benchmark anytime

```bash
cd ~/models/dgx_bundle/miaai35-tune
python3 bench_miaai35.py --tag my-run --thinking off
python3 stress_test.py
```

### Not done (needs download / approval)

- Smaller quants (UD-Q4_K_XL etc.) — not on disk; would trade quality for potential speed/memory  
- vLLM NVFP4 path for this 35B-A3B — HF stubs present, not loaded/measured here  
- Stopping ComfyUI / other GPU residents during pure decode (would need explicit approval if disruptive)

---

## 8. Addendum 2026-07-09 (later same night): PASS8/PASS9 — prompt-processing tune → **BALANCED v2**

The passes above optimized decode t/s and found it compute-bound. **Prompt processing was the
untested lever**: BALANCED v1 ran llama.cpp defaults (`n_batch 2048 / n_ubatch 512`). Measured with
`bench_pp.py` (server-side `timings`, 3 runs, medians) and `probe_concurrent.py` (small chat fired
mid-PP of a ~14k prompt — the multi-agent metric). Clean-window (0 busy slots) numbers:

| Config | PP @6.4k tok | PP @14k tok | Solo decode | Concurrent TTFT / decode | VRAM |
|---|---:|---:|---:|---:|---:|
| ub512 (v1) | 1337 t/s | 1275 t/s | 35.0–36.7 | 1.53s / **6.0 t/s** | 39542 MiB |
| **ub1024 = b4096 (PASS9, kept)** | **1611** | **1515** | 35.1–37.1 | **1.42s / 24.9 t/s** | 39762 |
| ub2048 = b4096 (PASS8, rejected) | 1661 | 1622 | 33.6–35.0 | 2.54s / 9.2 t/s | 40196 |

**Kept: PASS9 → promoted to `profiles/BALANCED.service` (v2).** v1 backup:
`backups/BALANCED.service.v1-ub512-2026-07-09`.

Verification (format per spec):
- Setting tested: `--batch-size 4096 --ubatch-size 1024` added to BALANCED
- Original PP tokens/sec: 1337 (6.4k) / 1275 (14k) → New: 1611 / 1515 → **+20% / +19%**
- Original long-ctx TTFT (harness 9.5k test): 7.56s → New: **6.29s** (−17%)
- Original decode: 35.80 t/s coding → New: **35.97** (unchanged)
- Concurrent small-chat during big PP: 1.53s/6.0 t/s → **1.42s/24.9 t/s** (~4× decode under load)
- Quality: 9.0/10 → **9.0/10** (full harness, all 4 tests) — 0% change
- VRAM: +220 MiB; RAM: ~unchanged
- Stability: stress_test.py 14/14 ok, 0 errors, sustained 35.7–42.5 t/s
- Decision: **KEEP** (BALANCED v2 live 21:47; real inference verified)

Notes: ub2048 rejected — +5% PP not worth 2× concurrent TTFT and −2 t/s solo decode. Ambient
background/lane-scan load depresses PP ~27% (976 vs 1337 t/s) — never compare contended vs clean runs.

### PASS10–12: `--cache-reuse` — REJECTED (no-op on this build; measured, 3 configs)

Hypothesis: agent repeat-calls with mid-prompt divergence could skip reprocessing unchanged KV
chunks. Probe: `probe_cache_reuse.py` (constant 2k head, changing status line, constant 7.5k tail,
canary code word). Result: repeat TTFT == cold TTFT (~5.6–6.0s @ ~9.2k tok) in ALL of:
- PASS10 `--cache-reuse 256` + KV q8_0
- PASS11 `--cache-reuse 256` + fp16 KV
- PASS12 `--cache-reuse 256` + fp16 KV + no mmproj

Journal proof the slot DID match (`sim_best = 0.182 > 0.100 thold, f_keep = 0.182`) yet no KV-shift
occurred and even the exact-prefix keep produced no measurable TTFT gain. Conclusion: KV-shift reuse
is a silent no-op on build a410713 (2026-07-05, unified KV cache) for this model. Canary stayed fresh
3/3 in every config (no stale-content risk observed). Re-test only after a llama.cpp upgrade.

**Transferable lesson (probe v1 failure):** llama-server slot matching needs LCP similarity > 0.10.
A prompt whose FIRST tokens change every call (timestamp first) gets sim ≈ 0 → lands on an LRU slot
→ zero cache benefit ever. Keep stable system preamble first, dynamic status later, in all agent
prompts.

## 9. Addendum 2026-07-09 (v3): PASS13 ngram speculative decode — **KEPT → BALANCED v3**

Build a410713 supports draft-model-free speculation (`--spec-type ngram-simple`). Drafts come from
the context itself and every token is verified by the full Q8 model — quality-lossless by
construction, no download. Measured (A/B with controls, clean windows):

| Workload | v2 (no spec) | v3 ngram-simple | Δ |
|---|---:|---:|---|
| Copy-heavy refactor (910 tok, correctness-checked 3/3) | 34.33 t/s | **74.48 t/s** | **+117%** |
| Prose essay (~650 tok) | 34.92 | 34.11 | −2% (noise) |
| Coding harness | 35.97 | 37.19 | +3% |
| Concurrent small-chat mid-PP (5 runs) | 2.65s / 8.63 t/s | 2.56s / 8.38 t/s | none |
| Full quality harness | 9.0/10 ×4 | 9.0/10 ×4 | none |
| Stress 14 req | 0 errors | 0 errors | — |

Journal confirms engagement: `draft acceptance = 0.243, mean len = 10`. VRAM unchanged (39.7 GB).
The earlier "concurrency regression" was 3-run noise; 5-run medians match.

- Setting tested: `--spec-type ngram-simple` added to BALANCED v2
- Decision: **KEEP** — v3 live 22:20; v2 backup `backups/BALANCED.service.v2-ub1024-2026-07-09`
- Wins where output repeats context: refactoring, code edits, quoting, JSON/tool loops — core agent work
- Not tried yet: other ngram variants (ngram-mod, ngram-map-k4v) — possible micro-gains, same method

## 10. Addendum 2026-07-09 (v4): PASS14/15 MTP GGUF + combined speculation — **KEPT → BALANCED v4**

User-approved download: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` UD-Q8_K_XL (39.1 GB → 
`~/models/dgx_bundle/downloads/mtp/`, size-verified) — **same Q8 quant** plus trained MTP draft
head; the config the MiaAI recipe was designed for. Spec decode is quality-lossless (main model
verifies every drafted token). Flags per recipe: `--spec-type draft-mtp,ngram-simple
--spec-draft-n-max 6 --spec-draft-p-min 0.85`.

| Workload | v2 (no spec) | v3 (ngram) | PASS14 (MTP only) | **v4 (MTP+ngram)** | v4 vs v2 |
|---|---:|---:|---:|---:|---:|
| Coding harness | 35.97 | 37.19 | 56.02 | 52.99 | **+47%** |
| Reasoning harness | 36.75 | 35.45 | 56.72 | 57.62 | **+57%** |
| Long-context harness | 36.54 | 36.88 | 54.47 | 57.03 (stress) | **+56%** |
| Copy-heavy refactor | 34.33 | 74.48 | 65.73 | **112.21** | **+227%** |
| Prose essay | 34.92 | 34.11 | 35.50 | 38.71 | **+11%** |
| Quality (harness) | 9.0 ×4 | 9.0 ×4 | 9.0 ×4 | **9.0 ×4** | none |
| Stress | clean | clean | — | **clean (44–69 t/s)** | — |
| VRAM | 39.7 GB | 39.7 GB | 42.4 GB | **42.5 GB** | +2.8 GB |

Concurrent probe on PASS14 ran under ambient agent load (busy=1) — not comparable to clean runs;
re-measure if multi-agent feel degrades. Load time ~11–41 s. Old GGUF kept on disk; revert =
`apply-profile.sh` any earlier profile (`backups/BALANCED.service.v3-ngram-2026-07-09` etc.).

- Decision: **KEEP — BALANCED v4 live 22:55, real inference verified**
- Main lesson: decode was "compute-bound" only per-token; speculation buys 1.5–3.3× by spending
  spare compute on verified lookahead. Quality unchanged because rejected drafts cost nothing.

## 11. Addendum 2026-07-10 (v5): spec-param tune + personalized rigorous eval — **BALANCED v5**

New quality gate: `bench_v5.py` — 19 objective checks built from the user's REAL workload
(Telegram queries + scheduled agent prompts): digest faithfulness, 3 hallucination/confusion traps
(incl. the logged lane-scan cross-attribution complaint), completeness enumeration,
Telegram-brief format compliance, 3 coding tasks EXECUTED against unit tests, 3 exact-answer
reasoning problems, OpenAI tool-call validity. No vibes scoring; every check machine-graded.
(3 early "failures" were grader bugs — the model was right each time; graders fixed.)

Speed lever: MTP draft params. Screened n-max {6,10,16} × p-min {0.85,0.75,0.6,0.5}:

| Config | Refactor t/s | Essay t/s |
|---|---:|---:|
| v4 (n6 p0.85) | 112 | 38.7 |
| n10 p0.85 | 137 | 44.9 |
| n16 p0.75 | 148 | 48.0 |
| **n6 p0.75 (KEPT)** | **159** | **51.3** |
| n6 p0.60 / p0.50 | 159 | 52 (plateau) |
| n10 p0.60 | 140 | 51.9 |

**BALANCED v5 = v4 + `--spec-draft-p-min 0.75`** (n-max stays 6). Verification is unconditional,
so lower p-min cannot change outputs — confirmed: **19/19 (100%) on bench_v5**, 9/10 ×4 on the
old harness, stress clean (60–72 t/s).

Canonical harness (clean): short 69.9 / coding 68.7 / reasoning 78.3 / long 68.7 t/s —
**coding +91%, reasoning +113% vs the original 35.8/36.8 baseline**. TTFT 0.22–0.26s short,
5.5s long. VRAM 42.5 GB (unchanged from v4).

NVFP4 note: the Blackwell FP4 units stay idle on this llama.cpp Q8 path by *design* — every
NVFP4/MXFP4 weight format is 4-bit and violates the Q8-only quality rule. The only quality-safe
way to exploit newer Blackwell kernels is a llama.cpp rebuild (declined so far; the v6 lever).

## 12. Addendum 2026-07-10: Q8 v5 vs unsloth NVFP4 (vLLM) — head-to-head

User-requested comparison. Downloaded `unsloth/Qwen3.6-35B-A3B-NVFP4` (26.5 GB safetensors →
`~/models/dgx_bundle/qwen-nvfp4/`, the launcher's expected dir for key `qwen`). Served with native
vLLM 0.23.0 on :8001 alongside live v5 (no llama-server kill — bypassed `free_memory_for_vllm`).
Flags = launcher fast profile: flashinfer, fp8 KV, marlin MoE, MTP spec (n=3), compressed-tensors,
gpu-util 0.35, max-len 65536. Gotchas hit: (1) flashinfer JIT needs `ninja` on PATH → prepend
`~/.venvs/hf-download/bin`; (2) vLLM packs ~2.3 tokens/SSE-chunk → chunk-counting UNDERCOUNTS
decode ~2.3×; must use `stream_options.include_usage` completion_tokens (speed_probe.py fixed).

**Speed** (same streaming probe, usage-corrected, both models resident — equal conditions):

| Test | Q8 v5 (llama.cpp :8889) | NVFP4 (vLLM :8001) | Winner |
|---|---:|---:|---|
| short decode | 36.6 t/s | 54.4 | NVFP4 +49% |
| coding decode | 54.5 | 68.3 | NVFP4 +25% |
| copy-heavy refactor | **121.1** | 76.9 | **Q8 +58%** (ngram spec) |
| essay decode | 38.6 | 51.1 | NVFP4 +32% |
| 8k-ctx decode | 36.6 | 48.8 | NVFP4 +33% |
| 8k-ctx TTFT (prefill) | 5.06 s | **1.47 s** | **NVFP4 3.4×** |
| short TTFT | 0.137 s | 0.127 s | tie |

**Quality:** bench_v5 (19 personalized objective checks): **both 19/19**. Hard-reasoning
tiebreaker (6 exact-answer items): **both 4/6 — missing the SAME two questions with the same
failure modes** (one token-budget truncation, one identical interpretation of an ambiguous
phrasing). No quality separation detectable at this eval's resolution.

**Ops trade-offs:** Q8 v5 loads in ~11 s (vLLM ~5.5 min first boot with JIT), has vision (mmproj),
128k ctx, systemd auto-heal, and agents fully wired. NVFP4 uses the Blackwell FP4 units, ~26.5 GB
weights (vs 38.4), text-only here, and the stock launcher path KILLS llama-server (use the manual
command in this section to run side-by-side). Both-resident = ~100/121 GB.

**Decision: v5 Q8 stays default** (quality rule + copy-heavy agent wins + ops maturity).
NVFP4 is a validated alternative lane — weights kept on disk; relaunch command above.

## 13. Addendum 2026-07-10: NVFP4 "v2" optimization campaign — matrix EXHAUSTED, v1 config is optimal

Attempt to tune NVFP4 past Q8-v5. Every lever measured or hard-blocked (vLLM 0.23, GB10):

| Candidate | Result |
|---|---|
| MTP spec depth 6 | **worse** — refactor +15% (77→88) but short −38%, essay −31% (vLLM re-runs ONE MTP layer per draft token; deep drafts decay, unlike llama.cpp) |
| MTP spec depth 4 | **no gain** — ≤spec-3 on all rows (refactor 79.5 ≈ 77) |
| `--moe-backend flashinfer_trtllm` | **unsupported** — "kernel does not support current device" (GB10/sm_121) |
| `--moe-backend flashinfer_cutlass` (±spec) | **unsupported** — checkpoint mixes NVFP4 experts with FP8 per-channel MoE layers; cutlass FP8 path rejects them. **Marlin is the only viable MoE backend for this checkpoint on this device.** |

**Verdict: NVFP4-optimal = the §12 config (marlin + MTP spec 3).** Standing comparison vs Q8-v5:
NVFP4 wins general decode +25–49% and 8k prefill 3.4×; Q8-v5 wins copy-heavy +58% (ngram spec —
vLLM 0.23 cannot combine ngram+MTP), vision, 11s loads, ops maturity. Quality identical (19/19 both;
same misses on the hard set). Which is "faster" is a workload question, not a config question.

Ops gotcha discovered: `pkill -f "vllm.entrypoints"` matches the invoking shell (exit 144, kills
your own command chain) — always use the bracket pattern `pkill -f "[v]llm.entrypoints"`.

## 14. Addendum 2026-07-11 (v6): llama.cpp rebuild a410713 → master 13f2b28 — **KEPT → BALANCED v6 (live)**

The last documented Q8-side lever, executed. Master built side-by-side in `~/llama.cpp-master/`
(git worktree, detached at 13f2b28 2026-07-11, 100 commits ahead; same cmake: CUDA arch 121,
Release, native). Old build untouched at `~/llama.cpp/build/` = revert path. Flags identical to
v5 — this is a pure engine swap.

Same-day, same-conditions comparison (fresh restart + warmup both sides, `speed_probe.py` ×3,
tags `v6base-v5-0711` / `v6cand-master-0711`):

| Test | v5 (a410713) | v6 (13f2b28) | Δ |
|---|---:|---:|---:|
| short | 45.8 t/s | 46.5 | +1.5% |
| coding | 65.8 | 69.5 | **+5.6%** |
| refactor | 149.5 | 154.7 | +3.4% |
| essay | 46.8 | 48.5 | +3.6% |
| ctx8k decode | 45.8 | 51.3 | **+12%** |
| ctx8k TTFT | 3.68s | 3.60s | −2% |
| model load | ~60s | ~30s | −50% |

Quality gate: **bench_v5 19/19** on master (results/v5-v6cand-master-0711-*.json), incl. tool-call
validity. No flag-surface changes (`--help` diff empty) — gains are internal (per-slot "graphs
reused" CUDA-graph reuse in logs; cuBLAS refactor #24216; ngram OOB fix #23936 also hardens our
`ngram-simple` path). Swap: unit ExecStart repointed to master binary (backup
`backups/BALANCED.service.v5-a410713-2026-07-11`), restarted in an idle window, live re-verified.
Total benchmark downtime 11:00:24–11:09:12 (~9 min), no cron collisions.

**`--cache-reuse` lever CLOSED — it was never a build bug.** Master logs the truth the old build
hid: with mmproj → `cache_reuse is not supported by multimodal`; without mmproj, even with fp16 KV
→ `cache_reuse is not supported by this context` (model-architecture level: this A3B/MTP context
doesn't support KV shifting). Probe confirmed full reprocess in both configs (repeat pp_n == cold).
§4's "build a410713 limitation" hypothesis is hereby corrected. Do not retest on future builds
unless that warning line disappears from load logs.

**Binary dependency note:** the master llama-server dynamically links libs inside
`~/llama.cpp-master/build/bin/` — do NOT delete that worktree while the service points at it.

Next Q8 lever: none configured; periodic rebuild of master is now the maintenance lever.
NVFP4-side lever unchanged: vLLM >0.23 with GB10 FP4 kernels.

## 15. Addendum 2026-07-11 (v7 candidate): NVFP4 GGUF on llama.cpp — ALL GATES PASSED, staged awaiting approval

The v7 campaign ("try the NVFP4 goodies"). Two lanes:

**Lane A — vLLM 0.24 FP4 kernels: CLOSED.** Tested via the on-disk `vllm/vllm-openai:v0.24.0`
Docker image (no venv touched, launched manually — never via start.sh). `flashinfer_trtllm`:
still "kernel does not support current device" on GB10. `flashinfer_cutlass`: still rejects the
checkpoint's FP8 per-channel MoE scheme (`QuantKey(f8e4m3fn,scale(f32,static,per_channel)...)`)
— identical blockers to 0.23. vLLM on GB10 remains marlin-only; no gain over §12. Lever now
requires a future vLLM/flashinfer release with sm_121 FP4 kernels.

**Lane B — NVFP4 GGUF on our own v6 llama.cpp engine: the winner.** llama.cpp master gained
native NVFP4 CUDA kernels (GGML_TYPE_NVFP4=40, MMVQ fuse #24481 — inside our v6 build).
Downloaded `mudler/Qwen3.6-35B-A3B-NVFP4-GGUF` (23.9 GB, sha256 verified `1690d042…`) — nvidia's
OFFICIAL NVFP4 weights converted tensor-for-tensor (`MOSTLY_NVFP4`, 241 native FP4 tensors, no
requant). Critically, **the MTP draft head survived conversion** → the full v5/v6 speculation
stack (`draft-mtp,ngram-simple` n6 p0.75) runs on NVFP4. No published alternative has this
(plunderstruck's is ROCm-tuned; llama-quantize has no NVFP4 target — only MXFP4_MOE).

Measured on :8890 **while live v6 stayed resident** (candidate handicapped, v6 numbers exclusive):

| Test | v6 Q8 | v7 NVFP4 | Δ |
|---|---:|---:|---:|
| short | 46.5 t/s | 51.1 | +10% |
| coding | 69.5 | **78.9** | +13.5% |
| refactor | 154.7 | **214.8** | **+39%** |
| essay | 48.5 | 50.2 | +3.5% |
| ctx8k decode | 51.3 | 51.2 | par |
| ctx8k TTFT | 3.60s | 3.27s | −9% |
| bench_v5 suite median | 62.8 | **81.1** | **+29%** |
| background PP | ~1611 t/s (v2) | ~2000 | +25% |
| weights RAM | 39.1 GB | **23.9 GB** | **−15 GB** |

**Quality gates (all passed):** bench_v5 **19/19**. NEW `hard6.py` (6 exact-answer items,
thinking ON, graded on a final ANSWER line): **v7 5/6 vs v6 4/6** at 12k budget; at 24k each
solved the one the other missed (v6: makespan; v7: cron-count) — parity, one long-thinker each.
Stress 14/14 clean ×2. **Vision works**: existing Q8-era `mmproj-BF16.gguf` attaches to the
NVFP4 base and correctly described a test image. Concurrency (5 runs): small-chat 46.6 t/s /
0.92s TTFT during big PP — healthy (ub2048 failure mode was 9 t/s / 2.5s).

**Harness lesson (trap #7):** hard-reasoning items with thinking ON truncated BOTH engines at
max_tokens 4096 → `finish_reason: length`, empty content, grader saw "FAIL". Thinking alone can
exceed 12k tokens. The thinking budget is part of the eval — check finish_reason before scoring.

**Status: DEPLOYED 2026-07-11 15:50 (user approved).** Applied via `apply-profile.sh
BALANCED_V7_NVFP4`, load_wait=11s, idle window (0 busy slots, 10 min clear of crypto cycle).
Live exclusive re-verification: coding 78.9 t/s, refactor 217.8, essay 53.2, ctx8k TTFT 3.08s;
bench_v5 **19/19** (suite median 74.7 t/s); vision confirmed on live endpoint; available RAM
59G → **83G** (+24G freed). Original staging plan below for the record:
`profiles/BALANCED_V7_NVFP4.service` (identical unit, model path → NVFP4 GGUF; mmproj kept) —
apply with `apply-profile.sh BALANCED_V7_NVFP4`; revert = `backups/BALANCED.service.v6-q8-2026-07-11`
+ Q8 GGUF kept on disk. Deciding trade-off: v7 wins everything measured AND frees ~10–15 GB;
the only argument for Q8 is 4-bit-caution sentiment — the data shows parity (3rd independent
parity result for this family).

## 16. Addendum 2026-07-11 (v8 campaign): options 5,1,2,3 — one big win, two closures, one split verdict

**Option 1 — spec re-screen on NVFP4: MAJOR WIN, staged as BALANCED_V8_NGRAMMOD.**
Master offers new ngram types (ngram-mod, ngram-map-k4v, ngram-cache, draft-dflash). Findings:
- `draft-mtp,ngram-mod` → coding 122 t/s (+63% vs same-day baseline 74.9) but refactor −16%.
- **Order matters in the spec list**: `draft-mtp,ngram-simple,ngram-mod` reverts to baseline
  (ngram-simple shadows mod), but **`draft-mtp,ngram-mod,ngram-simple` keeps both wins**.
- Deeper drafts (n8/p0.70) plateau — kept n6/p0.75.
- Clean confirm (exclusive-ish, runs 3): **coding 156.4 t/s (+98% vs live v7 78.9), refactor
  248.2 (+14%)**, essay/short par (contended), ctx8k 51.7. **bench_v5 19/19.**
- Staged: `profiles/BALANCED_V8_NGRAMMOD.service` (one-word change); v7 unit backed up as
  `backups/BALANCED.service.v7-specsimple-2026-07-11`.
- **DEPLOYED 2026-07-11 ~16:55 (user approved).** Live exclusive confirm: **coding 169.4 t/s,
  refactor 264.2**, essay 50.6, ctx8k 50.8 / TTFT 3.20s. Telegram end-to-end verified: 3/3
  gateways up + Daily News Digest agent cron triggered manually → ran on v8, delivered ok
  (16:57:38). Full arc v1→v8: coding 35.8 → 169.4 t/s (**4.7×**), refactor 34 → 264 (**7.8×**).

**Option 2 — ub2048: REJECTED AGAIN.** Concurrency probe (5 runs): small-chat 2.16s TTFT /
17.4 t/s during big PP (ub1024 healthy: 0.9s / 46.6). NVFP4's faster prefill shrank but did not
close the starvation window. Lever closed twice; do not retry without an architectural change.

**Option 3 — fp16 KV: REJECTED.** Same-conditions A/B: coding 74.9→65.3 (−13%), short −17%,
refactor −8%; only essay/ctx8k marginally up. q8_0 KV dequant is NOT the bottleneck. Keep q8_0.

**Option 5 — gpt-oss-120b (117B-A5.1B, native MXFP4 63.4GB → `~/models/dgx_bundle/gpt-oss-120b/`):
SPLIT VERDICT.** Benched solo on :8890 in a 24-min v7-downtime window (16:39–16:49 + probes).
- **Hard reasoning: clearly superior — hard6 6/6 in 5–29s/item**, including makespan which BOTH
  Qwen engines failed even at 24k thinking tokens. This is a smarter model.
- Speed: coding 41.5 t/s, refactor 88.6, essay 40.5, ctx8k TTFT 3.95s — roughly half of live v7,
  ~quarter of staged v8 coding. ngram-simple only (no MTP head).
- bench_v5: 16/19 — 3 fails UNADJUDICATED because bench_v5 saves no transcripts (tooling gap).
  Evidence of grader-compat issues: the "failed" cross-attribution detail text is actually the
  CORRECT trap answer, and gpt-oss emits U+2011 non-breaking hyphens in free prose (breaks ASCII
  regex greps) though it echoes ASCII fine when quoting. Needs a transcript-saving rerun to score
  fairly. No vision. Larger footprint (63.4 vs 23.9GB) but fits sole-model budget with ~30G spare.
- Candidate role if adopted: deep-reasoning specialist, NOT a v8 replacement (speed regression
  would hit every agent cron). Weights kept on disk pending user decision.

**Ops incident (own goal): the shared-model-path pkill.** Test-server cleanup used
`pkill -f "[q]36-…gguf"` — the model FILENAME, which the live :8889 server shares → every
screening cleanup also killed live (17 restarts 14:00–16:37; systemd auto-heal masked it;
crash-loop pager fired 16:30 = FALSE ALARM, corrected via Telegram). **Rule: kill test servers
by PORT (`pkill -f "[l]lama-server.*--port 8890"`), never by model path.**

## Artifact index

| Path | Purpose |
|---|---|
| `bench_miaai35.py` | Before/after harness |
| `stress_test.py` | Stability suite |
| `apply-profile.sh` / `revert-original.sh` | Safe profile swap + health wait |
| `profiles/*.service` | ORIGINAL, PASSn, MAX_SPEED, BALANCED, MAX_QUALITY |
| `results/bench-*.json` | Raw measurements |
| `backups/` | Pre-change unit copies |
| `hard6.py` | 6-item hard-reasoning tiebreaker (thinking ON, ANSWER-line graded, 12k+ budget) |
| `launch-master-8890.sh` / `launch-nvfp4-gguf-8890.sh` | side-by-side test-server launchers (:8890) |
| `profiles/BALANCED_V7_NVFP4.service` | staged v7 unit (NVFP4 GGUF), awaiting approval |

## v9 (2026-07-18) — engine rebuild on master 86a9c79
Same weights (nvidia NVFP4 GGUF) + same v8 flags; only the engine moved: 13f2b28 → 86a9c79
(93 commits; relevant: CUDA MoE gate/up activation dedup #25441). Built in ~/llama.cpp-v9
(git worktree — KEEP; llama.cpp-master v6 build untouched as revert).
bench_miaai35 same-night A/B (thinking off, zwell-extractor co-resident both runs):
short 71.4→79.3 (+11%), coding 77.4→80.0 (+3.3%), reasoning 84.8→89.4 (+5.5%),
long-ctx TTFT 6.24→4.87s (−22%); long-ctx tg 64.4 was cold-alloc noise (warm reruns 83.9/87.1).
Quality gate bench_v5 19/19 score 100 (D_brief 3/3 — no v4-style template regression).
Unit: .bak-2026-07-18-v8 = v8 revert. v10 candidates: spec-type sweep ngram-map-k/k4v/
ngram-cache; draft-dflash/eagle3 need sidecar models.

## v10 campaign (2026-07-18) — RESULT: flag space exhausted, config stays v9
Tested on the v9 engine (86a9c79), all 3-4 rep alternating A/B, novel-content probes:
- DFlash draft sidecar (z-lab 0.4B, block16, Alittlehammmer BF16 GGUF, 783M at
  ~/models/dgx_bundle/qwen-dflash/ — KEPT on disk): coding median 105.1 (n8 p0.3 tuned)
  vs MTP 103.8 (n10 p0.5) / 98.2 (prod n6 p0.75) = EQUAL WITHIN NOISE, +0.8G RAM.
  z-lab's "beats MTP 3.61x" numbers do NOT transfer to GB10 UMA (matches the Strix Halo
  field report: UMA is memory-bound; a dense drafter's forward cost eats the block win).
- n_max 6 vs 16: refactor NULL (476.0 vs 471.4 warm; earlier +8-12% was WARM-TABLE noise —
  ngram tables persist per server lifetime, alternate A/B on the SAME server state or lie).
  Coding NULL (98.6 vs 100.0 median over 4 alternating reps).
- p_min 0.75 vs 0.5: coding +5.7% = within +-30% single-run noise. Not shippable.
- ngram-map-k/k4v/cache NOT tested by decision: warm refactor already saturates at
  470-477 t/s with 100% draft acceptance — no headroom for a different echo drafter.
Remaining levers for v11: next engine rebuild when master moves (proven twice: v6, v9);
eagle3 sidecar if one appears for 35B-A3B (none exists as of 2026-07-18).
