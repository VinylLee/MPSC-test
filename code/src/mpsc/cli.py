"""CLI module for MPSC"""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml
from rich.console import Console

console = Console()


@click.group()
def main():
    """MPSC: Metamorphic Testing for Smart Contracts"""
    pass


@main.command()
@click.option(
    "--install-solc",
    is_flag=True,
    help="Install required solc binaries if they are absent.",
)
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Complete MPSC repository checkout to validate.",
)
@click.option(
    "--runtime-only",
    is_flag=True,
    help="Check Python, Solidity compilers, and the local chain only.",
)
@click.option("--json-output", is_flag=True, help="Print only machine-readable JSON.")
def doctor(
    install_solc: bool,
    project_root: Path,
    runtime_only: bool,
    json_output: bool,
):
    """Compile, deploy, and validate inputs before running."""

    from .doctor import run_doctor

    result = run_doctor(
        project_root=project_root,
        install_solc=install_solc,
        runtime_only=runtime_only,
    )
    if json_output:
        click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        color = "green" if result["status"] == "pass" else "red"
        console.print(f"[bold {color}]MPSC doctor: {result['status'].upper()}[/]")
        for item in result["checks"]:
            marker = {
                "pass": "[green]PASS[/green]",
                "info": "[yellow]INFO[/yellow]",
                "fail": "[red]FAIL[/red]",
            }[item["status"]]
            console.print(f" {marker} {item['name']}: {item['detail']}")
            if item["remediation"]:
                console.print(f"    fix: {item['remediation']}")
    if result["status"] != "pass":
        raise click.exceptions.Exit(1)


@main.command()
def list_mrs():
    """List all 38 non-executable MR templates."""
    import yaml

    catalog_path = Path("experiment-data/specification/mr_catalog.yaml")
    if not catalog_path.exists():
        console.print("[red]MR catalog not found[/red]")
        return

    with open(catalog_path, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    console.print("[bold]MPSC Metamorphic Relations[/bold]\n")
    console.print(
        f"{'ID':<10} {'Category':<12} {'Target Operation':<25} "
        f"{'Template instance executable'}"
    )
    console.print("-" * 76)

    for mr in catalog.get("mrs", []):
        exe = "Yes" if mr.get("automation", {}).get("executable", False) else "No"
        function_name = mr.get("subject", {}).get("function", "N/A")
        console.print(f"{mr['id']:<10} {mr['category']:<12} {function_name:<25} {exe}")


@main.command()
@click.argument("mr_id")
def describe_mr(mr_id: str):
    """Show one structured MR template."""
    import yaml

    catalog_path = Path("experiment-data/specification/mr_catalog.yaml")
    if not catalog_path.exists():
        console.print("[red]MR catalog not found[/red]")
        return

    with open(catalog_path, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    for mr in catalog.get("mrs", []):
        if mr["id"] == mr_id:
            console.print_json(
                json.dumps(mr, indent=2, ensure_ascii=False, default=str)
            )
            return

    console.print(f"[red]MR {mr_id} not found[/red]")


@main.command("run-mytoken")
@click.option(
    "--output",
    default="experiment-data/runs/mytoken-mr6",
    show_default=True,
    help="Canonical evidence output directory",
)
@click.option("--seed", default=20260727, show_default=True, type=int)
def run_mytoken(output: str, seed: int):
    """Run the canonical MyToken MR6 engineering-mutant matrix."""

    from .experiments.canonical_matrix import run_canonical_mytoken_matrix

    summary = run_canonical_mytoken_matrix(output, seed=seed)
    console.print_json(json.dumps(summary, ensure_ascii=False, default=str))


@main.command("verify-mutant-corpus")
@click.option(
    "--manifest",
    default="experiment-data/mutants/corpus_manifest.json",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--mutants-root",
    default="experiment-data/mutants",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--qualify",
    is_flag=True,
    help="Also recompile and minimally deploy all 18 public controls.",
)
def verify_mutant_corpus(
    manifest: Path,
    mutants_root: Path,
    qualify: bool,
):
    """Read-only validation of public engineering-mutant identities."""

    from .mutation.corpus import qualify_public_corpus, validate_public_corpus

    if qualify:
        result = qualify_public_corpus(
            manifest,
            mutants_root=mutants_root,
        )
    else:
        result = validate_public_corpus(
            manifest,
            mutants_root=mutants_root,
        )
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "pass":
        raise click.exceptions.Exit(1)


@main.command("verify-results-evidence")
@click.option(
    "--index",
    "index_path",
    default="experiment-data/results/results_evidence_index.json",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--subjects",
    "subject_manifest_path",
    default="experiment-data/subjects/subject_manifest.json",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--qualify-subjects",
    is_flag=True,
    help="Fresh-compile, deploy, and execute each subject's minimum profile checks.",
)
def verify_results_evidence(
    index_path: Path,
    subject_manifest_path: Path,
    qualify_subjects: bool,
):
    """Read-only verification of the five-subject and result evidence chain."""

    from .results_evidence import validate_results_evidence

    result = validate_results_evidence(
        index_path,
        subject_manifest_path=subject_manifest_path,
        qualify_subjects=qualify_subjects,
    )
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "pass":
        raise click.exceptions.Exit(1)


@main.command("run-mytoken-repetitions")
@click.option(
    "--output",
    default="experiment-data/runs/mytoken-optimization/repetitions",
    show_default=True,
    help="Repeated cell evidence output directory",
)
@click.option("--repetitions", default=10, show_default=True, type=int)
@click.option("--seed", default=20260727, show_default=True, type=int)
def run_mytoken_repetitions(output: str, repetitions: int, seed: int):
    """Run repeated MyToken engineering-control cells."""

    from .experiments.canonical_repetitions import (
        run_repeated_mytoken_matrix,
    )

    summary = run_repeated_mytoken_matrix(
        output,
        repetitions=repetitions,
        seed=seed,
    )
    console.print_json(json.dumps(summary, ensure_ascii=False, default=str))


@main.command("derive-mytoken-scores")
@click.option(
    "--repetitions",
    "repetitions_dir",
    default="experiment-data/results/canonical/mytoken_optimization/repetitions",
    show_default=True,
    help="Raw repeated evidence directory",
)
@click.option(
    "--output",
    default="experiment-data/runs/mytoken-optimization/scores",
    show_default=True,
    help="Eq.2/Eq.3 output directory",
)
@click.option("--tau", default=0.1, show_default=True, type=float)
def derive_mytoken_scores(repetitions_dir: str, output: str, tau: float):
    """Derive canonical Eq.2 kill vectors and Eq.3 mutation scores."""

    from .experiments.canonical_scores import derive_canonical_mutation_scores

    result = derive_canonical_mutation_scores(
        output,
        repetitions_dir=repetitions_dir,
        tau=tau,
    )
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@main.command("optimize-mytoken")
@click.option(
    "--scores",
    "scores_path",
    default="experiment-data/results/canonical/mytoken_optimization/scores/kill_vectors.json",
    show_default=True,
    help="Canonical Eq.2/Eq.3 evidence",
)
@click.option(
    "--config",
    "config_path",
    default="code/configs/experiments/mytoken_canonical_optimization.yaml",
    show_default=True,
    help="Explicit optimization scenario",
)
@click.option(
    "--output",
    default="experiment-data/runs/mytoken-optimization/algorithm1",
    show_default=True,
    help="Algorithm 1 output directory",
)
def optimize_mytoken(scores_path: str, config_path: str, output: str):
    """Run Eq.4-Eq.6 and Algorithm 1 on canonical vectors."""

    from .experiments.canonical_optimization import (
        run_canonical_optimization,
    )

    result = run_canonical_optimization(
        output,
        scores_path=scores_path,
        config_path=config_path,
    )
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@main.command("scan-mytoken-optimizer")
@click.option(
    "--scores",
    "scores_path",
    default="experiment-data/results/canonical/mytoken_optimization/scores/kill_vectors.json",
    show_default=True,
)
@click.option(
    "--config",
    "config_path",
    default="code/configs/experiments/mytoken_optimization_sensitivity.yaml",
    show_default=True,
)
@click.option(
    "--output",
    default="experiment-data/runs/mytoken-optimization/sensitivity",
    show_default=True,
)
def scan_mytoken_optimizer(
    scores_path: str,
    config_path: str,
    output: str,
):
    """Preserve all outcomes for unknown Algorithm 1 parameters."""

    from .experiments.optimization_sensitivity import (
        run_optimization_sensitivity,
    )

    result = run_optimization_sensitivity(
        output,
        scores_path=scores_path,
        config_path=config_path,
    )
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@main.command("compare-mytoken-optimization")
@click.option(
    "--report",
    default="experiment-data/runs/canonical-optimization-vs-supplied.md",
    show_default=True,
)
@click.option(
    "--json-output",
    default="experiment-data/runs/canonical-optimization-vs-supplied.json",
    show_default=True,
)
def compare_mytoken_optimization(report: str, json_output: str):
    """Compare canonical optimization with supplied values."""

    from .experiments.optimization_comparison import (
        write_optimization_comparison,
    )

    result = write_optimization_comparison(
        report,
        json_path=json_output,
    )
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@main.command("render-figures")
@click.option(
    "--processed-dir",
    default="experiment-data/processed",
    show_default=True,
    help="Published processed data directory",
)
@click.option(
    "--output",
    default="experiment-data/runs/figures",
    show_default=True,
    help="Figure output directory",
)
def render_figures(processed_dir: str, output: str):
    """Render figures from the published processed CSV files."""

    from .reporting import generate_figures

    summary = generate_figures(
        input_dir=processed_dir,
        output_dir=output,
    )
    console.print_json(json.dumps(summary, ensure_ascii=False, default=str))


@main.command("render-tables")
@click.option(
    "--processed-dir",
    default="experiment-data/processed",
    show_default=True,
    help="Published normalized CSV directory",
)
@click.option(
    "--output",
    default="experiment-data/runs/tables",
    show_default=True,
    help="Computed table output directory",
)
def render_tables(processed_dir: str, output: str):
    """Regenerate aggregate tables from published CSVs."""

    from .reporting import generate_computed_tables

    summary = generate_computed_tables(
        input_dir=processed_dir,
        output_dir=output,
    )
    console.print_json(json.dumps(summary, ensure_ascii=False, default=str))


@main.command("prepare-llm-offline")
@click.argument(
    "contract_source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--contract-id", required=True, help="Stable subject identifier.")
@click.option("--model-snapshot", required=True, help="Exact requested model snapshot.")
@click.option("--provider", required=True, help="Actual intended provider name.")
@click.option(
    "--request-date",
    required=True,
    help="Frozen request date in ISO YYYY-MM-DD form.",
)
@click.option("--temperature", type=float, default=None)
@click.option("--top-p", type=float, default=None)
@click.option("--max-tokens", type=int, default=None)
@click.option("--seed", type=int, default=None)
@click.option(
    "--seed-supported/--no-seed-supported",
    default=False,
    show_default=True,
    help="Whether the exact provider/model accepts the recorded seed.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
)
def prepare_llm_offline(
    contract_source: Path,
    contract_id: str,
    model_snapshot: str,
    provider: str,
    request_date: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    seed: int | None,
    seed_supported: bool,
    output: Path,
):
    """Prepare an explicitly incomplete, network-free LLM request bundle."""

    from .llm import LLMProtocolError, prepare_offline_run

    try:
        result = prepare_offline_run(
            contract_source,
            output,
            contract_id=contract_id,
            model_snapshot=model_snapshot,
            provider=provider,
            request_date=request_date,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            seed=seed,
            seed_supported=seed_supported,
        )
    except LLMProtocolError as error:
        raise click.ClickException(str(error)) from error
    console.print_json(json.dumps(result, ensure_ascii=False))


@main.command("prepare-llm-subjects")
@click.option("--model-snapshot", required=True, help="Exact intended model snapshot.")
@click.option("--provider", required=True, help="Actual intended provider name.")
@click.option("--request-date", required=True, help="ISO YYYY-MM-DD request date.")
@click.option("--temperature", type=float, default=None)
@click.option("--top-p", type=float, default=None)
@click.option("--max-tokens", type=int, default=None)
@click.option("--seed", type=int, default=None)
@click.option(
    "--seed-supported/--no-seed-supported",
    default=False,
    show_default=True,
)
@click.option(
    "--output",
    default="experiment-data/runs/llm",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
)
def prepare_llm_subjects(
    model_snapshot: str,
    provider: str,
    request_date: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    seed: int | None,
    seed_supported: bool,
    output: Path,
):
    """Prepare network-free request templates for all five subjects."""

    from .llm import LLMProtocolError, prepare_subject_requests

    try:
        result = prepare_subject_requests(
            output,
            provider=provider,
            model_snapshot=model_snapshot,
            request_date=request_date,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            seed=seed,
            seed_supported=seed_supported,
        )
    except (LLMProtocolError, OSError, yaml.YAMLError) as error:
        raise click.ClickException(str(error)) from error
    console.print_json(json.dumps(result, ensure_ascii=False))


@main.command("evaluate-llm-offline")
@click.argument(
    "run_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def evaluate_llm_offline(run_dir: Path):
    """Read-only verification of one completed seven-file LLM bundle."""

    from .llm import LLMProtocolError, evaluate_recorded_run

    try:
        result = evaluate_recorded_run(run_dir)
    except LLMProtocolError as error:
        raise click.ClickException(str(error)) from error
    console.print_json(json.dumps(result, ensure_ascii=False))


@main.command("summarize-vulnerability-reviews")
@click.argument(
    "package_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def summarize_vulnerability_reviews(package_dir: Path):
    """Validate reviews and summarize deduplicated confirmed findings."""

    from .review import ReviewProtocolError, summarize_confirmation_package

    try:
        result = summarize_confirmation_package(package_dir)
    except ReviewProtocolError as error:
        raise click.ClickException(str(error)) from error
    console.print_json(json.dumps(result, ensure_ascii=False))


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option("--solc-version", default=None, help="Solidity compiler version")
def compile(contract_path: str, solc_version: str | None):
    """Compile a Solidity contract"""
    from .solidity.compiler import compile_contract_solcx

    result = compile_contract_solcx(contract_path, solc_version)

    output = {
        "contract_name": result.contract_name,
        "compiler_version": result.compiler_version,
        "success": result.success,
        "abi_length": len(result.abi),
        "bytecode_length": len(result.bytecode),
        "warnings": result.warnings,
        "errors": result.errors,
    }

    console.print(json.dumps(output, indent=2))


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option("--function", required=True, help="Function name to call")
@click.option("--args", default="[]", help="Function arguments as JSON array")
@click.option("--solc-version", default=None, help="Solidity compiler version")
def call(contract_path: str, function: str, args: str, solc_version: str | None):
    """Call a contract function"""
    from .chain.local_backend import LocalChainBackend
    from .solidity.compiler import compile_contract_solcx

    compile_result = compile_contract_solcx(contract_path, solc_version)
    if not compile_result.success:
        console.print(f"[red]Compilation failed: {compile_result.errors}[/red]")
        return

    backend = LocalChainBackend()
    accounts = backend.get_accounts()

    receipt = backend.deploy(
        bytecode=compile_result.bytecode,
        abi=compile_result.abi,
        sender=accounts[0],
    )

    if not receipt.success:
        console.print("[red]Deployment failed[/red]")
        return

    func_args = json.loads(args)
    result, call_receipt = backend.call(
        contract_address=receipt.contract_address,
        abi=compile_result.abi,
        function_name=function,
        args=func_args,
        sender=accounts[0],
    )

    output = {
        "function": function,
        "args": func_args,
        "return_value": result,
        "gas_used": call_receipt.gas_used,
        "success": call_receipt.success,
    }

    console.print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
