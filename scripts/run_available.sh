#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
args=(run --locked python code/scripts/run_experiment.py available)
if [[ $# -gt 1 ]]; then
 echo "usage: $0 [output-under-experiment-data/runs]" >&2
 exit 2
elif [[ $# -eq 1 ]]; then
 args+=(--output "$1")
fi
echo "[MPSC] starting all available stages"
uv "${args[@]}"
