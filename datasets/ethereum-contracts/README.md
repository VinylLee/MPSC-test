# Ethereum contract snapshots

This directory is an independent dataset of Ethereum mainnet identities and
runtime-bytecode snapshots for four MPSC subjects. It does not alter or extend
`smartbugs-curated`.

## Contents

Each contract directory contains:

- `metadata.json`: address, canonical source/profile references, compiler,
  observation block, runtime size and SHA-256;
- `runtime-bytecode.hex`: the exact result of `eth_getCode` at the common
  observation block recorded in `manifest.json`.

The runtime data was queried through Ethereum JSON-RPC, not copied from an
Etherscan API response. Etherscan URLs in metadata are external human-readable
locators only.

## Evidence boundary

This dataset records chain identity and runtime code. It does not contain or
claim paper contract-level MR bindings, test executions, verdicts, mutation
results, initialization state, or Oracle evidence.

Source files remain in their canonical repository locations and are referenced
rather than duplicated. A source license is claimed only where the repository
already records one; `not_recorded_in_repository` is not a license grant.
