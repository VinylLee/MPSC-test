#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
expected_uv="0.11.29"
install_solc=false
if [[ "${1:-}" == "--install-solc" ]]; then
 install_solc=true
elif [[ $# -ne 0 ]]; then
 echo "usage: $0 [--install-solc]" >&2
 exit 2
fi

cd "$repo_root"
echo "[MPSC] bootstrap root=$repo_root"
actual_uv="$(uv --version 2>/dev/null || true)"
if [[ "$actual_uv" != "uv $expected_uv" && "$actual_uv" != "uv $expected_uv "* ]]; then
 echo "[MPSC] ERROR uv $expected_uv is required (found: ${actual_uv:-absent})" >&2
 exit 1
fi

echo "[MPSC] syncing CPython 3.11 environment from uv.lock"
uv sync --python 3.11 --locked --all-extras
uv run --locked python code/scripts/verify_build_contract.py --check-export

if [[ "$install_solc" == true ]]; then
 echo "[MPSC] installing/verifying Solidity 0.4.11, 0.4.16, 0.4.19, 0.7.6"
 echo "[MPSC] network may be required for compilers not already cached"
 uv run --locked mpsc doctor --install-solc --project-root "$repo_root"
else
 echo "[MPSC] read-only doctor; use --install-solc once if a compiler is absent"
 uv run --locked mpsc doctor --project-root "$repo_root"
fi
echo "[MPSC] bootstrap PASS"
