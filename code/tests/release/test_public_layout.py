import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path


def _public_files(*patterns: str) -> list[str]:
    """List release files from Git, or from an exported tree without .git."""

    if Path(".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z", *patterns],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            tracked = [
                path for path in result.stdout.decode("utf-8").split("\0") if path
            ]
            return [path for path in tracked if Path(path).is_file()]
    excluded_roots = {
        ".git",
        ".research",
        ".tmp",
        ".venv",
        "experiment-data/runs",
    }
    generated_parts = {
        "__pycache__",
        ".eggs",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
    files = []
    for path in Path(".").rglob("*"):
        normalized = path.as_posix().removeprefix("./")
        if not path.is_file() or any(
            normalized == root or normalized.startswith(f"{root}/")
            for root in excluded_roots
        ):
            continue
        if any(
            part in generated_parts or part.endswith(".egg-info") for part in path.parts
        ):
            continue
        if patterns and not any(
            fnmatch(path.name, pattern) or fnmatch(normalized, pattern)
            for pattern in patterns
        ):
            continue
        files.append(normalized)
    return sorted(files)


def test_public_repository_layout_is_separated():
    assert Path("code/src/mpsc").is_dir()
    assert Path("code/configs").is_dir()
    assert Path("code/tests").is_dir()
    assert Path("datasets/smartbugs-curated").is_dir()
    assert Path("experiment-data/processed").is_dir()
    assert Path("experiment-data/results/canonical").is_dir()
    assert not list(Path("experiment-data/results/reports").glob("*.md"))
    assert Path("README.md").is_file()
    assert Path("BUILD_MATRIX.json").is_file()
    assert Path("ARTIFACT_MANIFEST.json").is_file()


def test_private_material_is_not_published():
    tracked = _public_files()
    excluded = (".research/", "实验数据/", "实验数据origin/", "data/", "outputs/")
    assert "MPSC.pdf" not in tracked
    assert not [path for path in tracked if path.startswith(excluded)]


def test_build_matrix_declares_a_controlled_evidence_class():
    readme = Path("README.md").read_text(encoding="utf-8")
    matrix = json.loads(Path("BUILD_MATRIX.json").read_text(encoding="utf-8"))

    assert "Quick Start" in readme
    assert matrix["evidence_class"] in {"computed", "control", "verified"}


def test_reviewer_requested_artifacts_are_on_readme_first_screen():
    readme = Path("README.md").read_text(encoding="utf-8")
    first_screen = readme[:7000]

    assert "## Quick Start" in first_screen
    for term in (
        r".\scripts\bootstrap.ps1",
        r".\scripts\run_smoke.ps1",
        r".\scripts\run_available.ps1",
        "code/",
        "datasets/",
        "experiment-data/",
    ):
        assert term in first_screen


def test_readme_has_complete_rq_run_and_output_contract_without_overclaim():
    readme = Path("README.md").read_text(encoding="utf-8")
    lowered = readme.lower()

    for required_contract in (
        "## Quick Start",
        "## Repository layout",
        "## System requirements and native installation",
        r".\scripts\bootstrap.ps1 -InstallSolc",
        r".\scripts\run_smoke.ps1",
        r".\scripts\run_available.ps1",
        "exit 0",
    ):
        assert required_contract in readme

    for forbidden_claim in (
        "complete original artifacts",
        "complete re-execution",
        "fully re-executed",
        "full dataset package",
    ):
        assert forbidden_claim not in lowered


def test_readme_supported_cli_commands_have_live_help():
    documented_commands = ("doctor",)
    readme = Path("README.md").read_text(encoding="utf-8")

    for command in documented_commands:
        assert f"uv run --locked mpsc {command}" in readme
        result = subprocess.run(
            [sys.executable, "-m", "mpsc.cli", command, "--help"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Usage:" in result.stdout


def test_artifact_manifest_schema_paths_and_integrity_are_valid():
    result = subprocess.run(
        [sys.executable, "code/scripts/verify_artifact_manifest.py"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "pass"


def test_tracked_markdown_links_are_repository_local_and_exist():
    tracked = _public_files("*.md")
    link_pattern = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
    broken = []
    for raw_path in filter(None, tracked):
        markdown = Path(raw_path)
        for target in link_pattern.findall(markdown.read_text(encoding="utf-8")):
            clean = target.strip()
            if not clean or clean.startswith(("#", "mailto:")) or "://" in clean:
                continue
            clean = clean.split("#", 1)[0]
            if clean.startswith("<") and clean.endswith(">"):
                clean = clean[1:-1]
            if not (markdown.parent / clean).exists():
                broken.append(f"{markdown.as_posix()} -> {target}")
    assert not broken, "\n".join(broken)


def test_active_public_metadata_has_no_stale_root_paths():
    old_root = re.compile(
        r"""(?:[`"'])\s*(?:data|src|tests|configs|subjects|artifacts|outputs)/"""
    )
    old_roots = (
        "experiment-data/results/canonical/",
        "experiment-data/README.md",
    )
    tracked = _public_files("*.md", "*.json", "*.yaml", "*.yml")
    tracked.append("ARTIFACT_MANIFEST.json")
    stale = []
    for raw_path in filter(None, tracked):
        normalized = Path(raw_path).as_posix()
        if normalized.startswith(old_roots):
            continue
        for line_number, line in enumerate(
            Path(raw_path).read_text(encoding="utf-8").splitlines(), start=1
        ):
            if old_root.search(line):
                stale.append(f"{normalized}:{line_number}: {line.strip()}")
    assert not stale, "\n".join(stale)
