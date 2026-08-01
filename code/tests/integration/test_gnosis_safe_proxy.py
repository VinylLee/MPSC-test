import hashlib
import json
from pathlib import Path

import solcx
from mpsc.chain.local_backend import LocalChainBackend

SOURCE = Path("experiment-data/subjects/GnosisSafeProxy/GnosisSafeProxy.sol")
PROVENANCE = Path("experiment-data/provenance/gnosis_safe_proxy.json")


def _strip_solidity_metadata(bytecode: bytes) -> bytes:
    metadata_length = int.from_bytes(bytecode[-2:], "big")
    return bytecode[: -(metadata_length + 2)]


def test_verified_proxy_source_and_license_are_frozen():
    evidence = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    source = SOURCE.read_bytes().replace(b"\r\n", b"\n")

    assert (
        hashlib.sha256(source).hexdigest()
        == evidence["verified_source"]["repository_lf_source_sha256"]
    )
    assert (
        hashlib.sha256(source.rstrip(b"\n")).hexdigest()
        == evidence["verified_source"]["etherscan_lf_source_sha256"]
    )
    assert source.startswith(b"// SPDX-License-Identifier: LGPL-3.0-only\n")
    assert b"contract GnosisSafeProxy" in source


def test_proxy_compiles_deploys_and_matches_onchain_runtime_logic():
    evidence = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert "0.7.6" in {str(version) for version in solcx.get_installed_solc_versions()}
    solcx.set_solc_version("0.7.6")
    compiled = solcx.compile_source(
        SOURCE.read_text(encoding="utf-8"),
        output_values=["abi", "bin", "bin-runtime"],
        optimize=False,
    )["<stdin>:GnosisSafeProxy"]
    runtime_logic = _strip_solidity_metadata(bytes.fromhex(compiled["bin-runtime"]))

    assert len(runtime_logic) == evidence["chain"]["metadata_stripped_byte_length"]
    assert (
        hashlib.sha256(runtime_logic).hexdigest()
        == evidence["chain"]["metadata_stripped_runtime_sha256"]
    )

    backend = LocalChainBackend()
    singleton = backend.get_accounts()[1]
    receipt = backend.deploy(
        compiled["bin"],
        compiled["abi"],
        args=[singleton],
    )
    proxy_interface = [
        {
            "inputs": [],
            "name": "masterCopy",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]
    observed = backend.call_view(
        receipt.contract_address or "",
        proxy_interface,
        "masterCopy",
    )

    assert receipt.success
    assert observed.lower() == singleton.lower()
