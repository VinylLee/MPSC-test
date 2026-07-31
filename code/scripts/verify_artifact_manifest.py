"""Validate or refresh the reviewer-facing artifact manifest.

Controlled text files are hashed after CRLF and CR are normalized to LF.
Binary files are hashed byte-for-byte. Directory integrity is a deterministic
digest over explicit per-file records, not a file hash assigned to a directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "ARTIFACT_MANIFEST.json"
IGNORED_TREE_PARTS = {".git", ".venv", "__pycache__"}
IGNORED_TREE_SUFFIXES = {".pyc", ".pyo"}
LF_NORMALIZED_TEXT_SUFFIXES = frozenset(
    {
        ".cff",
        ".cfg",
        ".csv",
        ".ini",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".rst",
        ".sh",
        ".sol",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
LF_NORMALIZED_TEXT_BASENAMES = frozenset()
INTEGRITY_POLICY = {
    "text_strategy": "sha256_lf_normalized_text",
    "text_normalization": "replace CRLF with LF, then replace remaining CR with LF",
    "text_extensions": sorted(LF_NORMALIZED_TEXT_SUFFIXES),
    "text_basenames": sorted(LF_NORMALIZED_TEXT_BASENAMES),
    "binary_strategy": "sha256_bytes",
    "tree_strategy": "recursive_mixed_content_sha256",
    "tree_record_format": (
        "relative_path NUL digest_kind NUL content_sha256 LF, sorted by path"
    ),
}


def sha256_bytes(path: Path) -> str:
    """Return the byte-level SHA-256 digest for a binary file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_lf_normalized_text(path: Path) -> str:
    """Hash text bytes after portable newline normalization."""

    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def file_integrity(path: Path) -> dict[str, str]:
    """Return the declared content digest for one controlled file."""

    if (
        path.suffix.lower() in LF_NORMALIZED_TEXT_SUFFIXES
        or path.name in LF_NORMALIZED_TEXT_BASENAMES
    ):
        return {
            "strategy": INTEGRITY_POLICY["text_strategy"],
            "sha256": sha256_lf_normalized_text(path),
        }
    return {
        "strategy": INTEGRITY_POLICY["binary_strategy"],
        "sha256": sha256_bytes(path),
    }


def tree_integrity(path: Path) -> dict[str, Any]:
    """Return a cross-platform digest and count for each included tree file."""

    records: list[tuple[str, str, str]] = []
    for candidate in path.rglob("*"):
        relative = candidate.relative_to(path)
        if not candidate.is_file():
            continue
        if any(part in IGNORED_TREE_PARTS for part in relative.parts):
            continue
        if candidate.suffix.lower() in IGNORED_TREE_SUFFIXES:
            continue
        integrity = file_integrity(candidate)
        records.append(
            (relative.as_posix(), integrity["strategy"], integrity["sha256"])
        )
    records.sort()
    payload = "".join(
        f"{name}\0{digest_kind}\0{digest}\n" for name, digest_kind, digest in records
    )
    return {
        "strategy": INTEGRITY_POLICY["tree_strategy"],
        "file_count": len(records),
        "lf_normalized_text_file_count": sum(
            digest_kind == INTEGRITY_POLICY["text_strategy"]
            for _, digest_kind, _ in records
        ),
        "binary_file_count": sum(
            digest_kind == INTEGRITY_POLICY["binary_strategy"]
            for _, digest_kind, _ in records
        ),
        "sha256_tree": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "record_format": INTEGRITY_POLICY["tree_record_format"],
        "excluded": ["**/__pycache__/**", "**/*.pyc", "**/*.pyo"],
    }


def expected_integrity(path: Path, artifact_type: str) -> dict[str, Any]:
    """Build the integrity record required for a file or directory."""

    if artifact_type == "file":
        return file_integrity(path)
    if artifact_type == "directory":
        return tree_integrity(path)
    raise ValueError(f"unsupported artifact type: {artifact_type}")


def _safe_repository_path(raw_path: str) -> Path:
    posix = PurePosixPath(raw_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in raw_path:
        raise ValueError(
            f"path must be a normalized repository-relative path: {raw_path}"
        )
    resolved = (REPOSITORY_ROOT / Path(*posix.parts)).resolve()
    if resolved != REPOSITORY_ROOT and REPOSITORY_ROOT not in resolved.parents:
        raise ValueError(f"path escapes repository root: {raw_path}")
    return resolved


def refresh_manifest(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Refresh all declared integrity records in-place."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in payload["artifact_groups"]:
        path = _safe_repository_path(artifact["path"])
        artifact["integrity"] = expected_integrity(path, artifact["type"])
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def validate_manifest(manifest_path: Path = DEFAULT_MANIFEST) -> list[str]:
    """Return every schema, path, classification, and integrity error."""

    errors: list[str] = []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot read manifest: {error}"]

    if payload.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if payload.get("integrity_policy") != INTEGRITY_POLICY:
        errors.append("integrity_policy must match the verifier's declared policy")

    artifacts = payload.get("artifact_groups")
    if not isinstance(artifacts, list) or not artifacts:
        return errors + ["artifact_groups must be a non-empty array"]

    seen_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        prefix = f"artifact_groups[{index}]"
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif artifact_id in seen_ids:
            errors.append(f"{prefix}.id is duplicated: {artifact_id}")
        else:
            seen_ids.add(artifact_id)

        commands = artifact.get("commands", {})
        if not any(commands.get(key) for key in ("generate", "verify")):
            errors.append(f"{prefix}.commands requires generate or verify")

        raw_path = artifact.get("path")
        artifact_type = artifact.get("type")
        try:
            path = _safe_repository_path(raw_path)
        except (TypeError, ValueError) as error:
            errors.append(f"{prefix}.path: {error}")
            continue
        if not path.exists():
            errors.append(f"{prefix}.path does not exist: {raw_path}")
            continue
        if artifact_type == "file" and not path.is_file():
            errors.append(f"{prefix}.type says file: {raw_path}")
            continue
        if artifact_type == "directory" and not path.is_dir():
            errors.append(f"{prefix}.type says directory: {raw_path}")
            continue
        try:
            expected = expected_integrity(path, artifact_type)
        except ValueError as error:
            errors.append(f"{prefix}: {error}")
            continue
        if artifact.get("integrity") != expected:
            errors.append(
                f"{prefix}.integrity is stale; run "
                "python code/scripts/verify_artifact_manifest.py --write"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Manifest path (default: repository ARTIFACT_MANIFEST.json).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Refresh deterministic file and directory integrity records first.",
    )
    arguments = parser.parse_args()
    manifest = arguments.manifest.resolve()
    if arguments.write:
        refresh_manifest(manifest)
    errors = validate_manifest(manifest)
    result = {
        "manifest": manifest.relative_to(REPOSITORY_ROOT).as_posix(),
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
