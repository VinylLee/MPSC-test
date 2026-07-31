"""Tests for Solidity compiler"""

from mpsc.solidity.compiler import find_compatible_solc, normalize_pragma, parse_pragma


def test_parse_pragma():
    """Test pragma parsing"""
    source = "pragma solidity ^0.4.11;"
    pragma = parse_pragma(source)
    assert pragma == "^0.4.11"


def test_parse_pragma_with_spaces():
    """Test pragma parsing with extra spaces"""
    source = "pragma solidity >=0.4.0;"
    pragma = parse_pragma(source)
    assert pragma == ">=0.4.0"


def test_parse_pragma_missing():
    """Test pragma parsing when missing"""
    source = "contract Foo {}"
    pragma = parse_pragma(source)
    assert pragma is None


def test_normalize_pragma():
    """Test pragma normalization"""
    assert normalize_pragma("^0.4.11") == "0.4.11"
    assert normalize_pragma(">=0.4.0") == "0.4.0"
    assert normalize_pragma("0.4.25") == "0.4.25"


def test_find_compatible_solc():
    """Test finding compatible solc version"""
    versions = ["0.4.0", "0.4.11", "0.4.19", "0.4.24", "0.4.25"]

    assert find_compatible_solc("^0.4.11", versions) == "0.4.25"
    assert find_compatible_solc("0.4.11", versions) == "0.4.25"
