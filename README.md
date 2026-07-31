# MPSC

![CI](https://github.com/VinylLee/MPSC/actions/workflows/ci.yml/badge.svg)

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
 configs/       contract, MR, mutation, LLM, and experiment configs
 scripts/       Python orchestration/integrity helpers
 tests/        unit, integration, evidence, and release gates
scripts/         PowerShell bootstrap/run entry points
datasets/
 smartbugs-curated/  contracts grouped by vulnerability category
experiment-data/
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
