# ABOUTME: Tests for the command-line interface
# ABOUTME: Verifies exit codes, stream hygiene and messages when a store can't be read

import json
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from cookietuner import chrome, cli
from cookietuner.cli import app
from cookietuner.errors import CaptureTimeout, CookieStoreUnreadable
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


def test_capture_passes_the_requested_names_through(
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
            "--until",
            "session_id",
            "--until",
            "csrf_token",
            "--timeout",
            "42",
            "--proxy",
            "socks5://127.0.0.1:1080",
        ],
    )

    assert seen["until"] == {"session_id", "csrf_token"}
    assert seen["domain"] == "example.com"
    assert seen["timeout"] == 42.0
    assert seen["proxy"] == "socks5://127.0.0.1:1080"


def test_capture_without_until_waits_for_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No --until means the capture ends when the window closes."""
    seen: dict[str, object] = {}

    def fake_capture(**kwargs: object) -> list[Cookie]:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(cli, "capture_cookies", fake_capture)

    runner.invoke(app, ["capture", "--url", "https://example.com/login"])

    assert seen["until"] is None


def test_capture_reports_a_timeout_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(**kwargs: object) -> list[Cookie]:
        raise CaptureTimeout("Timed out after 5s waiting for session_id")

    monkeypatch.setattr(cli, "capture_cookies", time_out)

    result = runner.invoke(
        app, ["capture", "--url", "https://example.com/login", "--until", "session_id"]
    )

    assert result.exit_code == 1
    assert "session_id" in result.stderr
    assert result.stdout.strip() == ""


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
