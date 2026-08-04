#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ITYFUZZ_BIN="${ITYFUZZ_BIN:-ityfuzz}"
SOLC_BIN="${SOLC_BIN:-solc}"
SOURCE_DIR="${1:-$PROJECT_ROOT/experiment-data/comparison/ityfuzz/subjects/GovernanceToken}"
OUTPUT_DIR="${2:-$PROJECT_ROOT/experiment-data/runs/ityfuzz/governance-token}"
BUILD_DIR="$OUTPUT_DIR/build"

if [[ -d "$OUTPUT_DIR" ]] && [[ -n "$(find "$OUTPUT_DIR" -mindepth 1 -print -quit)" ]]; then
  echo "Output directory is not empty: $OUTPUT_DIR" >&2
  exit 2
fi

mkdir -p "$BUILD_DIR"
for source in "$SOURCE_DIR"/*.sol; do
  "$SOLC_BIN" --bin --abi "$source" -o "$BUILD_DIR" --overwrite
done

"$ITYFUZZ_BIN" evm -t "$BUILD_DIR/*" -d all -w "$OUTPUT_DIR" \
  | tee "$OUTPUT_DIR/fuzz.log"
