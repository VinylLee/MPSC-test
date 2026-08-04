#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ITYFUZZ_BIN="${ITYFUZZ_BIN:-ityfuzz}"
SOLC_BIN="${SOLC_BIN:-solc}"
CONTRACT_SOURCE="${1:-$PROJECT_ROOT/experiment-data/comparison/ityfuzz/subjects/MyToken.sol}"
CONTRACT_NAME="${2:-MyToken}"
OUTPUT_DIR="${3:-$PROJECT_ROOT/experiment-data/runs/ityfuzz/$CONTRACT_NAME}"
BUILD_DIR="$OUTPUT_DIR/build"

if [[ -d "$OUTPUT_DIR" ]] && [[ -n "$(find "$OUTPUT_DIR" -mindepth 1 -print -quit)" ]]; then
  echo "Output directory is not empty: $OUTPUT_DIR" >&2
  exit 2
fi

mkdir -p "$BUILD_DIR"
"$SOLC_BIN" --optimize --bin --abi "$CONTRACT_SOURCE" -o "$BUILD_DIR" --overwrite

if [[ ! -s "$BUILD_DIR/$CONTRACT_NAME.bin" ]] || [[ ! -s "$BUILD_DIR/$CONTRACT_NAME.abi" ]]; then
  echo "Compilation did not produce ABI/BIN for $CONTRACT_NAME" >&2
  exit 1
fi

args=(evm -t "$BUILD_DIR/*" -d all -w "$OUTPUT_DIR")
if [[ -n "${ITYFUZZ_CONSTRUCTOR_ARGS:-}" ]]; then
  args+=(--constructor-args "$ITYFUZZ_CONSTRUCTOR_ARGS")
fi
"$ITYFUZZ_BIN" "${args[@]}" | tee "$OUTPUT_DIR/fuzz.log"
