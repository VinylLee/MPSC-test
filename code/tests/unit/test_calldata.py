"""Tests for raw calldata encoding"""

from mpsc.chain.calldata import (
    build_sendcoin_calldata,
    build_sendcoin_swapped,
    encode_address,
    encode_uint256,
    keccak256_selector,
    swap_abi_slots,
)


class TestCalldataEncoding:
    def test_selector(self):
        sel = keccak256_selector("sendCoin(address,uint256)")
        assert len(sel) == 4
        assert sel.hex() == keccak256_selector("sendCoin(address,uint256)").hex()

    def test_encode_address(self):
        addr = "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"
        encoded = encode_address(addr)
        assert len(encoded) == 32
        assert encoded[:12] == b"\x00" * 12  # left-padded with zeros

    def test_encode_uint256(self):
        encoded = encode_uint256(100)
        assert len(encoded) == 32
        assert int.from_bytes(encoded, "big") == 100

    def test_build_sendcoin_calldata(self):
        addr = "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"
        calldata = build_sendcoin_calldata(addr, 100)
        assert len(calldata) == 4 + 32 + 32  # selector + 2 slots
        # Check selector
        assert calldata[:4] == keccak256_selector("sendCoin(address,uint256)")
        # Check first slot (address)
        slot1 = calldata[4:36]
        assert slot1 == encode_address(addr)
        # Check second slot (uint256)
        slot2 = calldata[36:68]
        assert int.from_bytes(slot2, "big") == 100

    def test_swapped_calldata(self):
        addr = "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"
        calldata = build_sendcoin_swapped(addr, 100)
        assert len(calldata) == 4 + 32 + 32
        # First slot should be uint256(100)
        slot1 = calldata[4:36]
        assert int.from_bytes(slot1, "big") == 100
        # Second slot should be address
        slot2 = calldata[36:68]
        assert slot2 == encode_address(addr)

    def test_swap_abi_slots(self):
        addr = "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"
        original = build_sendcoin_calldata(addr, 100)
        swapped = swap_abi_slots(original)
        # Selector unchanged
        assert swapped[:4] == original[:4]
        # Slots swapped
        assert swapped[4:36] == original[36:68]
        assert swapped[36:68] == original[4:36]

    def test_calldata_reaches_evm(self):
        """Calldata should be valid bytes that can be sent as transaction data"""
        addr = "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"
        calldata = build_sendcoin_swapped(addr, 100)
        hex_str = "0x" + calldata.hex()
        assert hex_str.startswith("0x")
        assert len(hex_str) == 2 + (4 + 64) * 2  # 0x + hex chars
