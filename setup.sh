#!/usr/bin/env bash
# One-command setup for miaai35-tune
set -euo pipefail
cd "$(dirname "$0")"

echo "==> miaai35-tune setup"
python3 -m venv .venv
./.venv/bin/pip -q install -U pip
./.venv/bin/pip -q install -r requirements.txt

BASE="${ZWELL_BASE:-${OPENAI_BASE:-http://127.0.0.1:8889}}"
echo
echo "Ready. Next (pick one):"
echo
echo "  1) Bench a live OpenAI-compatible server:"
echo "       ./.venv/bin/python bench_v5.py --base $BASE --tag local"
echo
echo "  2) Read the measured report:"
echo "       less REPORT.md"
echo
echo "  3) List profiles:"
echo "       ls profiles/"
echo
echo "Weights are NOT in this repo. Point llama-server at your Qwen3.6-35B GGUF first."
