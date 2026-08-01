from click.testing import CliRunner
from mpsc.cli import main

PUBLIC_COMMANDS = (
    "doctor",
    "run-mytoken",
    "render-tables",
    "render-figures",
)


def test_release_cli_exposes_the_four_supported_entry_points():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0, result.output
    for command in PUBLIC_COMMANDS:
        assert command in result.output


def test_each_release_command_has_stable_help():
    runner = CliRunner()

    for command in PUBLIC_COMMANDS:
        result = runner.invoke(main, [command, "--help"])
        assert result.exit_code == 0, (command, result.output)
        assert "Usage:" in result.output
