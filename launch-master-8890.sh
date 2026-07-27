#!/usr/bin/env bash
# v6 candidate: llama.cpp master build, EXACT BALANCED-v5 flags, test port 8890.
# Live service (llama-miaai35 on :8889) must be STOPPED first — both do not fit in RAM.
set -euo pipefail

BIN=$HOME/llama.cpp-master/build/bin/llama-server
LOG=$HOME/models/dgx_bundle/miaai35-tune/results/master-8890.log

if curl -s -m 2 localhost:8889/health >/dev/null 2>&1; then
  echo "REFUSING: live :8889 server is still up — stop llama-miaai35 first (memory)." >&2
  exit 1
fi

echo "launching master build on :8890, log -> $LOG"
exec "$BIN" \
  --model $HOME/models/dgx_bundle/downloads/mtp/Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf \
  --mmproj $HOME/models/dgx_bundle/qwen3.6-35b-a3b-ud/mmproj-BF16.gguf \
  --ctx-size 131072 \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --batch-size 4096 \
  --ubatch-size 1024 \
  --spec-type draft-mtp,ngram-simple \
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
