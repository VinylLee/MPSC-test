import runpy

MANIFEST_HELPERS = runpy.run_path("code/scripts/verify_artifact_manifest.py")
file_integrity = MANIFEST_HELPERS["file_integrity"]
tree_integrity = MANIFEST_HELPERS["tree_integrity"]


def test_controlled_text_hash_normalizes_lf_crlf_and_cr(tmp_path):
    lf = tmp_path / "example.json"
    crlf = tmp_path / "example-crlf.json"
    cr = tmp_path / "example-cr.json"
    lf.write_bytes(b'{\n "value": 1\n}\n')
    crlf.write_bytes(b'{\r\n "value": 1\r\n}\r\n')
    cr.write_bytes(b'{\r "value": 1\r}\r')

    expected = file_integrity(lf)

    assert expected["strategy"] == "sha256_lf_normalized_text"
    assert file_integrity(crlf) == expected
    assert file_integrity(cr) == expected


def test_binary_hash_preserves_byte_differences(tmp_path):
    lf = tmp_path / "sample.bin"
    crlf = tmp_path / "sample-crlf.bin"
    lf.write_bytes(b"\x00line\n\xff")
    crlf.write_bytes(b"\x00line\r\n\xff")

    lf_integrity = file_integrity(lf)
    crlf_integrity = file_integrity(crlf)

    assert lf_integrity["strategy"] == "sha256_bytes"
    assert crlf_integrity["strategy"] == "sha256_bytes"
    assert lf_integrity["sha256"] != crlf_integrity["sha256"]


def test_tree_digest_is_portable_for_text_and_strict_for_binary(tmp_path):
    lf_tree = tmp_path / "lf"
    crlf_tree = tmp_path / "crlf"
    lf_tree.mkdir()
    crlf_tree.mkdir()
    (lf_tree / "record.md").write_bytes(b"first\nsecond\n")
    (crlf_tree / "record.md").write_bytes(b"first\r\nsecond\r\n")
    (lf_tree / "payload.bin").write_bytes(b"\x00\x01")
    (crlf_tree / "payload.bin").write_bytes(b"\x00\x01")

    first = tree_integrity(lf_tree)
    second = tree_integrity(crlf_tree)

    assert first == second
    assert first["strategy"] == "recursive_mixed_content_sha256"
    assert first["lf_normalized_text_file_count"] == 1
    assert first["binary_file_count"] == 1

    (crlf_tree / "payload.bin").write_bytes(b"\x00\x02")

    assert tree_integrity(crlf_tree)["sha256_tree"] != first["sha256_tree"]
