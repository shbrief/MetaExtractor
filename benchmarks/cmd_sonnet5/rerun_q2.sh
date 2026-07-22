#!/usr/bin/env bash
# Rerun one model end-to-end (extract + eval) against the current working tree,
# which now includes the Q2 Europe PMC full-text fallback in fetcher.py.
# Usage: rerun_q2.sh <model> <outdir> <logfile>
set -euo pipefail
MODEL="$1"; OUTDIR="$2"; LOG="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
export ANTHROPIC_API_KEY="$(cat "$HOME/OmicsMLRepo/MetaHarmonizerEval/vignettes/keys/llm_baseline")"

{
  echo "=== rerun_q2 model=$MODEL outdir=$OUTDIR started $(date) ==="
  python "$HERE/bench.py" run  "$HERE/manifest.json" "$HERE/$OUTDIR" --model "$MODEL" --force
  echo "=== extraction done $(date); scoring ==="
  python "$HERE/bench.py" eval "$HERE/manifest.json" "$HERE/$OUTDIR"
  echo "=== rerun_q2 model=$MODEL DONE $(date) ==="
} >"$HERE/$LOG" 2>&1
