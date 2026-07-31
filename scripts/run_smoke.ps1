[CmdletBinding()]
param(
  [string]$Output
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $RepoRoot
try {
  $Arguments = @(
    "run", "--locked", "python",
    "code/scripts/run_experiment.py", "smoke"
  )
  if ($Output) {
    $Arguments += @("--output", $Output)
  }
  Write-Host "[MPSC] starting smoke run"
  & uv @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "smoke run failed; inspect run_summary.json and logs."
  }
}
finally {
  Pop-Location
}
