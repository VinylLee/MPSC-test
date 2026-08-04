# ItyFuzz comparison campaign

This directory contains the fixed Solidity inputs used to compare MPSC with
ItyFuzz and the static-analysis baselines. The campaign is integrated into the
same code, configuration, evidence, and reporting layers as the rest of the
repository.

## Component map

| Component | Repository location |
| --- | --- |
| Solidity subjects and harnesses | `experiment-data/comparison/ityfuzz/subjects/` |
| Campaign and deployment configuration | `code/configs/comparison_tools/ityfuzz_campaign.yaml` and `code/configs/comparison_tools/ityfuzz/` |
| ItyFuzz implementation | `tools/ityfuzz/` at commit `35b7f08962fdd0c2e02df7ef8a43164913d514d9` |
| Execution entry points | `scripts/run_ityfuzz.sh` and `scripts/run_ityfuzz_multi.sh` |
| Coverage, corpora, traces, replays, ABI/BIN, and Slither output | `experiment-data/results/canonical/ityfuzz/` |
| Normalized RQ4/RQ6 values | `experiment-data/processed/ityfuzz/` |
| Deterministic figure renderer | `code/src/mpsc/reporting/ityfuzz.py` |
| Published extended figures | `experiment-data/results/reports/ityfuzz/` |

## Validate and reproduce

Initialize the pinned tool source and validate all campaign paths, subject
hashes, recorded-run counts, and the ItyFuzz revision:

```bash
git submodule update --init --recursive
uv run --locked mpsc verify-ityfuzz-campaign
```

With `ityfuzz` and a compatible `solc` on `PATH`, run one subject or the
governance multi-contract fixture:

```bash
scripts/run_ityfuzz.sh
scripts/run_ityfuzz_multi.sh
```

Both scripts derive paths from the repository root, refuse to overwrite a
nonempty output directory, and write new runs below
`experiment-data/runs/ityfuzz/`. `ITYFUZZ_BIN`, `SOLC_BIN`, and
`ITYFUZZ_CONSTRUCTOR_ARGS` select local executables and constructor values.

Replay a saved input directly with ItyFuzz, for example:

```bash
ityfuzz evm -r experiment-data/results/canonical/ityfuzz/runs/bectoken/corpus/4_replayable
```

Estimate the first appearance of a characteristic `batchTransfer` input:

```bash
uv run --locked mpsc analyze-ityfuzz-detection-time \
  experiment-data/results/canonical/ityfuzz/runs/bectoken
```

## Static analysis and figures

The npm lock file pins Solhint 6.0.1. The subjects intentionally include
vulnerable patterns, so a nonzero Solhint exit status records findings rather
than invalidating the campaign input.

```bash
npm ci
npm run version:solhint
npm run lint:solhint
```

The saved Slither JSON is at
`experiment-data/results/canonical/ityfuzz/static-analysis/slither-report.json`.
A fresh Slither run requires a compiler matching each subject's pragma.

The four recorded RQ PDFs remain in
`experiment-data/results/canonical/ityfuzz/recorded-figures/`. RQ4 and RQ6
values are also normalized into CSV files so the extended figures can be
regenerated deterministically:

```bash
uv run --locked mpsc render-ityfuzz-figures \
  --output experiment-data/runs/ityfuzz-figures
```

`node_modules/` and Rust `target/` are reconstructed dependency/build caches.
The npm lock file, ItyFuzz `Cargo.lock`, and pinned submodule revision retain
the inputs needed to reproduce them without storing machine-specific cache
contents in the project history.
