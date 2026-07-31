[CmdletBinding()]
param(
  [switch]$InstallSolc
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExpectedUv = "0.11.29"

Push-Location $RepoRoot
try {
  Write-Host "[MPSC] bootstrap root=$RepoRoot"
  $UvOutput = (& uv --version 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or $UvOutput -notmatch "^uv $([regex]::Escape($ExpectedUv))\b") {
    throw "uv $ExpectedUv is required (found: $UvOutput). Install that exact version and retry."
  }
  Write-Host "[MPSC] syncing CPython 3.11 environment from uv.lock"
  & uv sync --python 3.11 --locked --all-extras
  if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed. Check network/proxy access or restore uv.lock."
  }
  Write-Host "[MPSC] validating locked build contract"
  & uv run --locked python code/scripts/verify_build_contract.py
  if ($LASTEXITCODE -ne 0) {
    throw "locked build metadata is inconsistent."
  }
  if ($InstallSolc) {
    Write-Host "[MPSC] installing/verifying Solidity 0.4.11, 0.4.16, 0.4.19, 0.7.6"
    Write-Host "[MPSC] network may be required for compilers not already cached"
    & uv run --locked mpsc doctor --project-root $RepoRoot --runtime-only --install-solc
  }
  else {
    Write-Host "[MPSC] read-only doctor; use -InstallSolc once if a compiler is absent"
    & uv run --locked mpsc doctor --project-root $RepoRoot --runtime-only
  }
  if ($LASTEXITCODE -ne 0) {
    throw "doctor failed. Follow the printed remediation and rerun bootstrap."
  }
  Write-Host "[MPSC] bootstrap PASS"
}
finally {
  Pop-Location
}
