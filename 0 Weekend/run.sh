#!/usr/bin/env bash
# Usage: ./run.sh [hackreport args], e.g. ./run.sh all --years 2024 2025
set -euo pipefail
cd "$(dirname "$0")"

MODEL="gemma3:4b"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if ! command -v ollama >/dev/null; then
  echo "Ollama is not installed: brew install --cask ollama-app" >&2
  exit 1
fi

if ! curl -s -m 3 localhost:11434 >/dev/null; then
  echo "Starting Ollama..."
  open -a Ollama
  for _ in $(seq 1 30); do
    curl -s -m 3 localhost:11434 >/dev/null && break
    sleep 2
  done
  curl -s -m 3 localhost:11434 >/dev/null || { echo "Ollama did not start" >&2; exit 1; }
fi

ollama list | grep -q "^$MODEL" || ollama pull "$MODEL"

if grep -q "set-your-email" hackreport/fetch.py; then
  echo "Note: set your contact email in USER_AGENT in hackreport/fetch.py" >&2
fi

ARGS=("$@")
[ ${#ARGS[@]} -eq 0 ] && ARGS=(all)
.venv/bin/python -W ignore -m hackreport "${ARGS[@]}"

echo
echo "Report: $PWD/data/report.md"
echo "CSV:    $PWD/data/events.csv"
