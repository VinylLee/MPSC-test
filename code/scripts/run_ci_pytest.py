"""Run pytest and expose a bounded failure traceback in GitHub Actions."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _escape_workflow_command(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    command = [sys.executable, "-m", "pytest", *sys.argv[1:]]
    result = subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    print(output, end="")
    if result.returncode == 0:
        return 0

    diagnostic = "\n".join(output.splitlines()[-160:])
    print(
        "::error title=Pytest failure details::" + _escape_workflow_command(diagnostic)
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n### Pytest failure details\n\n```text\n")
            handle.write(diagnostic)
            handle.write("\n```\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
