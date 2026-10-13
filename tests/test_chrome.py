# ABOUTME: Tests for Chrome cookie extraction
# ABOUTME: Verifies we can read and decrypt Chrome cookies on macOS

from datetime import datetime
from pathlib import Path

import pytest

from cookietuner import chrome
from cookietuner.chrome import get_cookies, list_profiles
from cookietuner.domain import domain_matches
from cookietuner.errors import CookieStoreUnreadable
from cookietuner.models import Cookie


def _skip_if_unreadable(call):
    """Runs a backend call, skipping the test where macOS denies the store."""
    try:
        return call()
    except CookieStoreUnreadable as exc:
        pytest.skip(str(exc))


def test_get_cookies_returns_list_of_cookies() -> None:
    """get_cookies should return a list of Cookie objects."""
    cookies = _skip_if_unreadable(get_cookies)
    assert isinstance(cookies, list)
    if cookies:
        assert isinstance(cookies[0], Cookie)


def test_cookie_has_required_fields() -> None:
    """Cookie should have all expected fields."""
    cookie = Cookie(
        domain=".example.com",
        name="session_id",
        value="abc123",
        path="/",
        expires=datetime(2025, 12, 31),
        is_secure=True,
        is_httponly=True,
        same_site="strict",
    )
    assert cookie.domain == ".example.com"
    assert cookie.name == "session_id"
    assert cookie.value == "abc123"
    assert cookie.path == "/"
    assert cookie.expires == datetime(2025, 12, 31)
    assert cookie.is_secure is True
    assert cookie.is_httponly is True
    assert cookie.same_site == "strict"


def test_cookie_defaults() -> None:
    """Cookie should have sensible defaults for optional fields."""
    cookie = Cookie(
        domain=".example.com",
        name="test",
        value="123",
        path="/",
    )
    assert cookie.expires is None
    assert cookie.is_secure is False
    assert cookie.is_httponly is False
    assert cookie.same_site is None


def test_get_cookies_by_domain() -> None:
    """get_cookies should filter by domain when specified."""
    cookies = _skip_if_unreadable(lambda: get_cookies(domain="google.com"))
    for cookie in cookies:
        assert domain_matches(cookie.domain, "google.com")


def test_list_profiles_returns_browser_profiles() -> None:
    """list_profiles should return available Chrome profiles."""
    profiles = _skip_if_unreadable(list_profiles)
    assert isinstance(profiles, list)
    # Should have at least Default profile if Chrome is installed
    if profiles:
        default_profiles = [p for p in profiles if p.profile_name == "Default"]
        assert len(default_profiles) <= 1  # At most one Default


class _UnreadableDirectory:
    """Stands in for a profile folder macOS lets us stat but not list."""

    def exists(self) -> bool:
        return True

    def iterdir(self) -> None:
        raise PermissionError(1, "Operation not permitted")


def test_list_profiles_reports_an_unreadable_profile_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A folder we may stat but not list should be named in the error."""
    monkeypatch.setattr(chrome, "CHROME_BASE_PATH", _UnreadableDirectory())

    with pytest.raises(CookieStoreUnreadable, match="Operation not permitted"):
        list_profiles()


def test_get_cookies_reports_an_unreadable_cookie_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cookie file we may stat but not read should be named in the error."""
    store = tmp_path / "Cookies"
    store.write_bytes(b"")
    monkeypatch.setattr(chrome, "_get_cookie_path", lambda profile="Default": store)

    def deny(src: object, dst: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(chrome.shutil, "copy2", deny)

    with pytest.raises(CookieStoreUnreadable, match=str(store)):
        get_cookies()


def test_get_cookies_leaves_the_keychain_alone_when_unreadable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unreadable store should fail before prompting for Keychain access."""
    store = tmp_path / "Cookies"
    store.write_bytes(b"")
    monkeypatch.setattr(chrome, "_get_cookie_path", lambda profile="Default": store)

    def deny(src: object, dst: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(chrome.shutil, "copy2", deny)

    keychain_reads = []
    monkeypatch.setattr(
        chrome, "_get_encryption_key", lambda: keychain_reads.append(1) or b"k" * 16
    )

    with pytest.raises(CookieStoreUnreadable):
        get_cookies()

    assert keychain_reads == []
