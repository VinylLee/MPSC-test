"""Code-only source release construction."""

from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path
from typing import Any


def build_release_archive(
    output_path: str | Path,
    *,
    version: str = "0.1.0",
    ref: str = "HEAD",
) -> dict[str, Any]:
    """Create a deterministic git archive and adjacent SHA-256 checksum."""

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"mpsc-{version}"
    subprocess.run(
        [
            "git",
            "archive",
            "--worktree-attributes",
            "--format=zip",
            f"--prefix={prefix}/",
            f"--output={output}",
            ref,
        ],
        check=True,
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(
        f"{digest} {output.name}\n",
        encoding="ascii",
    )
    with zipfile.ZipFile(output) as archive:
        entry_count = len(archive.namelist())
    return {
        "schema_version": 1,
        "version": version,
        "ref": ref,
        "archive": str(output),
        "sha256": digest,
        "checksum": str(checksum_path),
        "entry_count": entry_count,
    }
