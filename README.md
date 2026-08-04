# MPSC

![CI](https://github.com/VinylLee/MPSC-dataset/actions/workflows/ci.yml/badge.svg)

Implementation and dataset for **"MPSC: A Metamorphic
Testing Approach based on Mutable Parameters for Smart Contracts."**

## Repository status notice

This is the pre-acceptance (v0.1) version of the repository. The codebase is
still in an early, unorganized state. After the paper is accepted, we will
take the time to clean up, organize, and document the code, then re-upload
the repository as a polished release. Please treat the current contents as
work-in-progress.

## Quick Start

The commands below are used both locally and by CI. They assume a complete
checkout, uv 0.11.29 on `PATH`, PowerShell 7, and the repository root as the
current directory. Bootstrap may use the network for the first locked
dependency and Solidity compiler download. Later runs are offline.

```powershell
.\scripts\bootstrap.ps1 -InstallSolc
.\scripts\run_smoke.ps1
.\scripts\run_available.ps1
```

Success means all three commands exit 0.


## Repository layout

```text
code/
 src/mpsc/       Python package and CLI
 configs/       contract, MR, mutation, LLM, comparison, and experiment configs
 scripts/       Python orchestration/integrity helpers
 tests/        unit, integration, evidence, and release gates
scripts/         PowerShell bootstrap/run entry points
tools/
 ityfuzz/        vendored, revision-frozen implementation used by the comparison campaign
datasets/
 smartbugs-curated/  contracts grouped by vulnerability category
 ethereum-contracts/ Ethereum mainnet identities and frozen runtime-bytecode snapshots
doc/             processed experimental data, charts, and supporting documents
experiment-data/
 comparison/     fixed inputs for comparison-tool campaigns
 subjects/       five subject sources and qualification manifest
 specification/    structured MR/operator facts
 mutants/       generated mutants per subject contract
 processed/      normalized data and computed aggregate tables
 results/
  canonical/     versioned reference/control evidence
  reports/      comparisons, figures, discrepancies, and status
 runs/         execution output (git-ignored)
```

## System requirements and native installation

- CPython 3.11 (the locked baseline; metadata also accepts 3.12–3.13);
- uv **0.11.29**;
- Solidity compilers **0.4.11, 0.4.16, 0.4.19, and 0.7.6**;
- Windows with PowerShell 7;
- network access only for the first dependency/compiler install.

The PowerShell scripts locate the repository from their own paths, so they can
also be called from another working directory. In read-only/cached mode omit
`-InstallSolc`. Bootstrap refuses a different uv version,
syncs the environment from `uv.lock`, validates the locked build metadata,
and ends with the runtime doctor.

Useful read-only diagnostics from the repository root:

```powershell
uv run --locked mpsc doctor
uv run --locked mpsc --help
```

Each command exits nonzero on failure. `doctor` explains how to install a
missing compiler.

## CLI Commands

All commands run as `uv run --locked mpsc <command>` and exit nonzero on
failure. Read-only commands never modify tracked artifacts; generative
commands write their outputs under `experiment-data/runs/`.

### Diagnostics and verification

| Command | Purpose |
| --- | --- |
| `doctor` | Compile, deploy, and validate inputs before running. Explains how to install a missing compiler. |
| `verify-mutant-corpus` | Read-only validation of the public engineering-mutant identities (counts, hashes, and bidirectional disk inventory). |
| `verify-results-evidence` | Read-only verification of the five-subject qualification and the result-evidence chain. |
| `verify-ityfuzz-campaign` | Validate the frozen revision marker, 11 campaign inputs, and four recorded run directories. |
| `analyze-ityfuzz-detection-time <run-dir>` | Locate the first matching vulnerability-triggering corpus item. |

### MR catalog browsing

| Command | Purpose |
| --- | --- |
| `list-mrs` | List all 38 non-executable MR templates from the specification catalog. |
| `describe-mr` | Show one structured MR template as JSON. |

### Example MyToken experiments

| Command | Purpose |
| --- | --- |
| `run-mytoken` | Run the example MyToken MR6 engineering-mutant matrix. |
| `run-mytoken-repetitions` | Run repeated MyToken engineering-control cells. |
| `derive-mytoken-scores` | Derive kill vectors and mutation scores from raw cells. |
| `optimize-mytoken` | Run the MR-set optimization algorithm on vectors. |
| `scan-mytoken-optimizer` | Preserve all outcomes for the unknown optimization parameters. |
| `compare-mytoken-optimization` | Compare optimization results with supplied values. |

### Computed tables and figures

| Command | Purpose |
| --- | --- |
| `render-tables` | Regenerate aggregate tables from the published processed CSVs. |
| `render-figures` | Render figures from the published processed CSV files. |
| `render-ityfuzz-figures` | Render the extended five-method comparison figures from published CSV files. |

### Comparison-tool campaign

ItyFuzz is integrated as a vendored comparison tool rather than a detached
artifact bundle or submodule. The frozen upstream revision is recorded in
`tools/ityfuzz/.mpsc-pinned-commit`, and the full source tree ships under
`tools/ityfuzz/`, so no initialization step is needed after cloning. Validate
the recorded campaign and optionally render the extended figures:

```powershell
uv run --locked mpsc verify-ityfuzz-campaign
uv run --locked mpsc render-ityfuzz-figures \
  --output experiment-data/runs/ityfuzz-figures
```

The smoke and available entry points both run `verify-ityfuzz-campaign`, so CI
checks the vendored tool and the recorded campaign evidence on every push.

The fixed Solidity inputs are under
`experiment-data/comparison/ityfuzz/subjects/`; ABI/BIN outputs, coverage,
corpora, traces, vulnerability replays, static-analysis output, and recorded
figures are under `experiment-data/results/canonical/ityfuzz/`. New
shell-based runs use `scripts/run_ityfuzz.sh` or `scripts/run_ityfuzz_multi.sh` and always
write below the ignored `experiment-data/runs/` tree.

For static analysis, install the locked Node dependencies with `npm ci`, then
run `npm run lint:solhint` as a manual aid. The locked rules target modern
Solidity, so the legacy 0.4.x subjects report many style findings; treat the
output as informational rather than a gate. Slither can analyze the same fixed
subjects with `slither experiment-data/comparison/ityfuzz/subjects` after
selecting a compatible Solidity compiler.

### LLM protocol

| Command | Purpose |
| --- | --- |
| `prepare-llm-offline` | Prepare an explicitly incomplete, network-free LLM request bundle. |
| `prepare-llm-subjects` | Prepare network-free request templates for all five subjects. |
| `evaluate-llm-offline` | Read-only verification of one completed seven-file LLM bundle. |
| `summarize-vulnerability-reviews` | Validate reviews and summarize deduplicated confirmed findings. |

### Solidity helpers

| Command | Purpose |
| --- | --- |
| `compile` | Compile a Solidity contract. |
| `call` | Call a contract function. |
