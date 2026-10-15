# ABOUTME: Tests for the command-line interface
# ABOUTME: Verifies exit codes, stream hygiene and messages when a store can't be read

import json
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from cookietuner import chrome, cli
from cookietuner.cli import app
from cookietuner.errors import (
    CaptureError,
    CaptureIncomplete,
    CaptureTimeout,
    ChromeNotFound,
    CookieStoreUnreadable,
    PasswordsExtensionMissing,
    ProfileAccessDenied,
)
from cookietuner.models import Cookie

runner = CliRunner()

DENIED = "Chrome's profile data is unreadable"

SECRET = "sup3rs3cr3t-cookie-value"

# Crashes inside the CLI, with the secret held only in a frame local. Run in a
# subprocess because CliRunner catches exceptions before Typer prints them.
CRASHING_CLI = f"""
import sys
from cookietuner import cli

def boom(**kwargs):
    leaked_cookie_value = {SECRET!r}
    raise RuntimeError("the capture broke")

cli.capture_cookies = boom
sys.argv = ["cookietuner", "capture", "--url", "https://example.com/login"]
cli.app()
"""


def test_cookies_exits_nonzero_when_the_store_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cookies should report the denial instead of raising a traceback."""

    def deny(domain: str | None = None, profile: str = "Default") -> None:
        raise CookieStoreUnreadable(DENIED)

    monkeypatch.setattr(chrome, "get_cookies", deny)

    result = runner.invoke(app, ["cookies", "-b", "chrome"])

    assert result.exit_code == 1
    assert DENIED in result.output


def test_profiles_still_lists_other_browsers_when_chrome_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One unreadable browser shouldn't take the whole listing down."""

    def deny() -> None:
        raise CookieStoreUnreadable(DENIED)

    monkeypatch.setattr(chrome, "list_profiles", deny)

    result = runner.invoke(app, ["profiles"])

    assert result.exit_code == 0
    assert DENIED in result.output


def test_capture_writes_only_cookies_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capture output has to pipe into a secret store, so chatter goes to stderr."""
    captured = [
        Cookie(domain="example.com", name="session_id", value="s3cr3t", path="/")
    ]

    def fake_capture(**kwargs: object) -> list[Cookie]:
        return captured

    monkeypatch.setattr(cli, "capture_cookies", fake_capture)

    result = runner.invoke(
        app,
        [
            "capture",
            "--url",
            "https://example.com/login",
            "-d",
            "example.com",
            "-o",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [
        {
            "domain": "example.com",
            "name": "session_id",
            "value": "s3cr3t",
            "path": "/",
            "is_secure": False,
            "is_httponly": False,
            "is_expired": False,
        }
    ]
    assert "Sign in" in result.stderr


def test_capture_passes_every_condition_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_capture(**kwargs: object) -> list[Cookie]:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(cli, "capture_cookies", fake_capture)

    runner.invoke(
        app,
        [
            "capture",
            "--url",
            "https://example.com/login",
            "-d",
            "example.com",
            "-d",
            "auth.example.com",
            "--until",
            "session_id",
            "--until",
            "sb-*-auth-token",
            "--until-value",
            "uid!=anon_*",
            "--until-url",
            "*/dashboard*",
            "--settle",
            "2",
            "--timeout",
            "42",
            "--proxy",
            "socks5://127.0.0.1:1080",
        ],
    )

    assert seen["until"] == {"session_id", "sb-*-auth-token"}
    assert seen["domains"] == ["example.com", "auth.example.com"]
    assert seen["until_values"] == ["uid!=anon_*"]
    assert seen["until_url"] == "*/dashboard*"
    assert seen["settle"] == 2.0
    assert seen["timeout"] == 42.0
    assert seen["proxy"] == "socks5://127.0.0.1:1080"


def test_capture_without_conditions_waits_for_the_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No conditions means the capture ends when the browser does."""
    seen: dict[str, object] = {}

    def fake_capture(**kwargs: object) -> list[Cookie]:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(cli, "capture_cookies", fake_capture)

    result = runner.invoke(app, ["capture", "--url", "https://example.com/login"])

    assert seen["until"] == set()
    assert seen["until_values"] == []
    assert seen["until_url"] is None
    assert "Close the browser" in result.stderr


def test_capture_reports_a_timeout_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(**kwargs: object) -> list[Cookie]:
        raise CaptureTimeout("Timed out after 5s waiting for session_id")

    monkeypatch.setattr(cli, "capture_cookies", time_out)

    result = runner.invoke(
        app, ["capture", "--url", "https://example.com/login", "--until", "session_id"]
    )

    assert result.exit_code == CaptureTimeout.exit_code
    assert "session_id" in result.stderr
    assert result.stdout.strip() == ""


@pytest.mark.parametrize(
    "error",
    [
        CaptureTimeout,
        CaptureIncomplete,
        ChromeNotFound,
        ProfileAccessDenied,
        PasswordsExtensionMissing,
    ],
)
def test_each_capture_failure_has_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch, error: type[CaptureError]
) -> None:
    """A script should be able to tell these apart without reading messages."""

    def fail(**kwargs: object) -> list[Cookie]:
        raise error("no good")

    monkeypatch.setattr(cli, "capture_cookies", fail)

    result = runner.invoke(app, ["capture", "--url", "https://example.com/login"])

    assert result.exit_code == error.exit_code
    # 2 is what the command line itself exits with on a bad option.
    assert result.exit_code not in (0, 2)


def test_exit_codes_are_distinct() -> None:
    codes = [
        error.exit_code
        for error in (
            CaptureTimeout,
            CaptureIncomplete,
            ChromeNotFound,
            ProfileAccessDenied,
            PasswordsExtensionMissing,
        )
    ]
    assert len(set(codes)) == len(codes)


def test_a_malformed_condition_is_a_usage_error() -> None:
    """A typo should cost nothing, so it's refused before Chrome opens.

    The real capture runs here: the conditions are parsed first, so this never
    reaches the browser.
    """
    result = runner.invoke(
        app,
        [
            "capture",
            "--url",
            "https://example.com/login",
            "--until-value",
            "no-separator",
        ],
    )

    assert result.exit_code == 2


def test_progress_lines_go_to_stderr_and_survive_glob_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A glob like sb-[0-9]* would otherwise be eaten as console markup."""

    def report(**kwargs: object) -> list[Cookie]:
        on_progress = kwargs["on_progress"]
        assert callable(on_progress)
        on_progress(["sb-[0-9]*-auth-token", "URL */dashboard*"])
        return []

    monkeypatch.setattr(cli, "capture_cookies", report)

    result = runner.invoke(
        app,
        ["capture", "--url", "https://example.com/login", "--until", "sb-[0-9]*"],
    )

    assert result.exit_code == 0
    assert "sb-[0-9]*-auth-token" in result.stderr
    assert "URL */dashboard*" in result.stderr
    assert result.stdout.strip() == "[]" or result.stdout.strip() == ""


def test_a_crash_does_not_print_cookie_values() -> None:
    """Tracebacks must not dump frame locals; they hold cookies and crypto keys."""
    result = subprocess.run(
        [sys.executable, "-c", CRASHING_CLI],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert "the capture broke" in result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr
