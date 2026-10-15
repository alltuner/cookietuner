# ABOUTME: Keeps the documentation honest about the CLI and the Python API
# ABOUTME: Fails when an option or a public name ships without being written up

import re
from pathlib import Path

import pytest
import typer.main

import cookietuner
from cookietuner.cli import app

DOCS = Path(__file__).resolve().parent.parent / "docs"
USAGE = (DOCS / "usage.md").read_text()
API = (DOCS / "api.md").read_text()

COMMANDS = typer.main.get_command(app).commands  # type: ignore[attr-defined]


def options(command_name: str) -> list[str]:
    """Every option the command accepts, long and short, as typed."""
    flags: list[str] = []
    for parameter in COMMANDS[command_name].params:
        flags.extend(parameter.opts)
        flags.extend(parameter.secondary_opts)
    return [flag for flag in flags if flag.startswith("-") and flag != "--help"]


def documents(flag: str) -> bool:
    """Whether the usage docs mention this exact flag.

    Bounded, so --until isn't counted as documented by --until-value, and -d
    isn't matched inside a word.
    """
    return bool(re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", USAGE))


@pytest.mark.parametrize("command_name", sorted(COMMANDS))
def test_every_command_option_is_in_the_usage_docs(command_name: str) -> None:
    """Taken from the command itself, so a new option can't ship undocumented."""
    undocumented = [flag for flag in options(command_name) if not documents(flag)]
    assert undocumented == []


@pytest.mark.parametrize("name", cookietuner.__all__)
def test_every_public_name_is_documented_in_the_api_reference(name: str) -> None:
    """A heading or a table cell, so a passing mention somewhere doesn't count."""
    documented = re.search(
        rf"^#+ +{re.escape(name)}\b|`{re.escape(name)}`\s*\|", API, re.MULTILINE
    )
    assert documented, f"{name} is in __all__ but has no entry in docs/api.md"


@pytest.mark.parametrize("name", sorted(cookietuner.__all__))
def test_every_public_name_is_importable_from_the_package(name: str) -> None:
    assert hasattr(cookietuner, name)


def test_every_capture_exit_code_is_documented() -> None:
    """The exit codes are the contract a script relies on."""
    for error in (
        cookietuner.CaptureTimeout,
        cookietuner.CaptureIncomplete,
        cookietuner.ChromeNotFound,
        cookietuner.ProfileAccessDenied,
        cookietuner.PasswordsExtensionMissing,
    ):
        assert f"| {error.exit_code} |" in API, (
            f"exit code {error.exit_code} ({error.__name__}) is not in docs/api.md"
        )
