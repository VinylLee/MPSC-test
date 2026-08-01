"""Serialization utilities for MPSC - handles HexBytes and binary data"""

from __future__ import annotations

from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize an object for JSON serialization"""
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, bytes):
        return obj.hex()
    elif isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    elif hasattr(obj, "hex"):
        # HexBytes or similar
        return obj.hex() if obj.hex().startswith("0x") else "0x" + obj.hex()
    else:
        return str(obj)


def format_address(addr: Any) -> str:
    """Format an address to checksum hex string"""
    if isinstance(addr, bytes):
        return "0x" + addr.hex()
    return str(addr)


def format_tx_hash(tx_hash: Any) -> str:
    """Format a transaction hash to hex string"""
    if isinstance(tx_hash, bytes):
        return "0x" + tx_hash.hex()
    return str(tx_hash)
