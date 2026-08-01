import tomllib
from pathlib import Path

import yaml


def test_mit_license_is_present_and_scoped():
    license_text = Path("LICENSE").read_text(encoding="utf-8")

    assert license_text.startswith("MIT License")
    assert "Permission is hereby granted" in license_text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in license_text


def test_citation_has_software_and_verified_primary_authors():
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))

    assert citation["cff-version"] == "1.2.0"
    assert citation["version"] == "0.1.0"
    assert citation["license"] == "MIT"
    assert citation["repository-code"].endswith("VinylLee/MPSC")
    assert [
        author["family-names"] for author in citation["preferred-citation"]["authors"]
    ] == ["Chen", "Li", "Feng", "Cai", "Sun", "Shi"]
    assert "DOI are not stated" in citation["preferred-citation"]["notes"]


def test_third_party_notice_excludes_unlicensed_material_from_mit_scope():
    notice = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "rights in third-party contracts" in notice
    assert "original licenses" in notice
    assert "`MPSC.pdf`" in notice
    assert "not covered by the software MIT license" in notice


def test_python_release_range_and_baseline_are_explicit():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["requires-python"] == ">=3.11,<3.14"
    assert Path(".python-version").read_text(encoding="utf-8").strip() == "3.11"


def test_universal_and_pip_locks_are_portable_and_not_repo_bound():
    uv_lock = Path("uv.lock").read_text(encoding="utf-8")
    pip_lock = Path("requirements-lock.txt").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.11, <3.14"' in uv_lock
    assert 'name = "pywin32"' in uv_lock
    assert "pywin32==312 ; sys_platform == 'win32'" in pip_lock
    assert "git+https://github.com/VinylLee/MPSC-dataset" not in pip_lock
    assert "\n-e " not in pip_lock


def test_ci_has_all_release_gates():
    workflow = yaml.load(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert set(workflow["jobs"]) == {
        "lint",
        "readme-entrypoints",
    }
    assert workflow["permissions"] == {"contents": "read"}
    workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "--ignore" not in workflow_text
    assert "--exclude" not in workflow_text
