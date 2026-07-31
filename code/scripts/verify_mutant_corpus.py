"""Validate the public engineering-mutant corpus without modifying evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "code" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from mpsc.mutation.corpus import (  # noqa: E402
    qualify_public_corpus,
    validate_public_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("experiment-data/mutants/corpus_manifest.json"),
    )
    parser.add_argument(
        "--mutants-root",
        type=Path,
        default=Path("experiment-data/mutants"),
    )
    parser.add_argument(
        "--qualify",
        action="store_true",
        help="Recompile and minimally deploy every listed mutant.",
    )
    arguments = parser.parse_args()
    validator = qualify_public_corpus if arguments.qualify else validate_public_corpus
    result = validator(
        arguments.manifest,
        base_dir=REPOSITORY_ROOT,
        mutants_root=arguments.mutants_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
