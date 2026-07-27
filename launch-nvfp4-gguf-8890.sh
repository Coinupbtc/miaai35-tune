#!/usr/bin/env bash
# v7 candidate lane B: mudler NVFP4 GGUF (nvidia official FP4 weights) on the v6 llama.cpp
# master engine, port 8890. ~24GB weights + ~5GB KV — CAN run alongside live v6 (:8889),
# but NOT alongside the vLLM benchmark container (stop that first).
# SPEC_TYPE overridable: full stack default; use "ngram-simple" if the GGUF lacks MTP layers.
set -euo pipefail

BIN=$HOME/llama.cpp-master/build/bin/llama-server
MODEL=$HOME/models/dgx_bundle/qwen-nvfp4-gguf/q36-35b-a3b-nvfp4.gguf
LOG=$HOME/models/dgx_bundle/miaai35-tune/results/nvfp4-gguf-8890.log
SPEC_TYPE="${SPEC_TYPE:-draft-mtp,ngram-simple}"

avail=$(free -g | awk '/^Mem:/{print $7}')
if [ "$avail" -lt 48 ]; then
  echo "REFUSING: only ${avail}G available; need ~33G for this server + 15G floor." >&2
  exit 1
fi

echo "launching NVFP4 GGUF on :8890 (spec: $SPEC_TYPE), log -> $LOG"
exec "$BIN" \
  --model "$MODEL" \
  --ctx-size 131072 \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --batch-size 4096 \
  --ubatch-size 1024 \
  --spec-type "$SPEC_TYPE" \
  --spec-draft-n-max 6 \
  --spec-draft-p-min 0.75 \
  --host 127.0.0.1 \
  --port 8890 \
  --temperature 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --min-p 0.0 \
  --presence-penalty 0.0 \
  --repeat-penalty 1.0 \
  --chat-template-kwargs '{"preserve_thinking":true}' \
  >"$LOG" 2>&1
