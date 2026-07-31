"""Validate the subject qualification layer and published result lineage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "code" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mpsc.results_evidence import validate_results_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("experiment-data/results/results_evidence_index.json"),
    )
    parser.add_argument(
        "--subjects",
        type=Path,
        default=Path("experiment-data/subjects/subject_manifest.json"),
    )
    parser.add_argument(
        "--qualify-subjects",
        action="store_true",
        help="Fresh-compile, deploy, and execute all declared qualification steps.",
    )
    arguments = parser.parse_args()
    result = validate_results_evidence(
        arguments.index,
        subject_manifest_path=arguments.subjects,
        base_dir=REPOSITORY_ROOT,
        qualify_subjects=arguments.qualify_subjects,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
