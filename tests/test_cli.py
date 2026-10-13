# ABOUTME: Tests for the command-line interface
# ABOUTME: Verifies exit codes and messages when a browser's store can't be read

import pytest
from typer.testing import CliRunner

from cookietuner import chrome
from cookietuner.cli import app
from cookietuner.errors import CookieStoreUnreadable

runner = CliRunner()

DENIED = "Chrome's profile data is unreadable"


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
