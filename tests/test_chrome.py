# ABOUTME: Tests for Chrome cookie extraction
# ABOUTME: Verifies we can read and decrypt Chrome cookies on macOS

from datetime import datetime

from cookietuner.chrome import get_cookies, list_profiles
from cookietuner.models import Cookie


def test_get_cookies_returns_list_of_cookies() -> None:
    """get_cookies should return a list of Cookie objects."""
    cookies = get_cookies()
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
    cookies = get_cookies(domain="google.com")
    for cookie in cookies:
        assert "google" in cookie.domain.lower()


def test_list_profiles_returns_browser_profiles() -> None:
    """list_profiles should return available Chrome profiles."""
    profiles = list_profiles()
    assert isinstance(profiles, list)
    # Should have at least Default profile if Chrome is installed
    if profiles:
        default_profiles = [p for p in profiles if p.profile_name == "Default"]
        assert len(default_profiles) <= 1  # At most one Default
