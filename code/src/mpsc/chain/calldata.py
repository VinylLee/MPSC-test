"""Raw calldata construction for MPSC - bypasses Web3 ABI validation"""

from __future__ import annotations

import hashlib
from typing import Any


def function_selector(signature: str) -> bytes:
    """Compute 4-byte function selector from signature"""
    return hashlib.sha3_256(signature.encode()).digest()[:4]


def keccak256_selector(signature: str) -> bytes:
    """Compute function selector using keccak256 (Ethereum standard)"""
    from web3 import Web3

    return Web3.keccak(text=signature)[:4]


def encode_address(addr: str) -> bytes:
    """Encode address as 32-byte ABI slot (left-padded with zeros)"""
    addr_clean = addr.replace("0x", "").lower()
    return bytes.fromhex(addr_clean.zfill(64))


def encode_uint256(value: int) -> bytes:
    """Encode uint256 as 32-byte ABI slot"""
    return value.to_bytes(32, byteorder="big")


def build_calldata(function_sig: str, args: list[tuple[str, Any]]) -> bytes:
    """Build raw calldata for a function call

    Args:
      function_sig: e.g., "sendCoin(address,uint256)"
      args: list of (type, value) tuples

    Returns:
      Complete calldata bytes
    """
    selector = keccak256_selector(function_sig)

    encoded_args = b""
    for arg_type, arg_value in args:
        if arg_type == "address":
            encoded_args += encode_address(arg_value)
        elif arg_type == "uint256":
            encoded_args += encode_uint256(arg_value)
        elif arg_type == "uint":
            encoded_args += encode_uint256(arg_value)
        elif arg_type == "bool":
            encoded_args += encode_uint256(1 if arg_value else 0)
        else:
            raise ValueError(f"Unsupported type: {arg_type}")

    return selector + encoded_args


def swap_abi_slots(calldata: bytes) -> bytes:
    """Swap the first two 32-byte argument slots in calldata

    For sendCoin(address,uint256):
    - Original: selector + address_slot + uint256_slot
    - Swapped: selector + uint256_slot + address_slot
    """
    if len(calldata) < 4 + 64:
        raise ValueError("Calldata too short to swap slots")

    selector = calldata[:4]
    slot1 = calldata[4:36]
    slot2 = calldata[36:68]
    rest = calldata[68:]

    return selector + slot2 + slot1 + rest


def build_sendcoin_calldata(to_address: str, amount: int) -> bytes:
    """Build calldata for sendCoin(address,uint256)"""
    return build_calldata(
        "sendCoin(address,uint256)",
        [
            ("address", to_address),
            ("uint256", amount),
        ],
    )


def build_sendcoin_swapped(to_address: str, amount: int) -> bytes:
    """Build swapped calldata for sendCoin(address,uint256)

    Swaps the two argument slots:
    - Slot 1 (originally address) now contains uint256(amount)
    - Slot 2 (originally uint256) now contains address(to_address)
    """
    selector = keccak256_selector("sendCoin(address,uint256)")

    # Swap: first slot gets uint256, second slot gets address
    slot1 = encode_uint256(amount)  # was address, now uint256
    slot2 = encode_address(to_address)  # was uint256, now address

    return selector + slot1 + slot2
