# ABOUTME: Tests for Safari cookie extraction
# ABOUTME: Verifies Safari binarycookies parsing

from cookietuner.safari import get_cookies, list_profiles


def test_list_profiles_returns_safari_profile() -> None:
    """list_profiles should return Safari profile if Safari is installed."""
    profiles = list_profiles()
    assert isinstance(profiles, list)
    # Safari has at most one profile
    assert len(profiles) <= 1
    if profiles:
        assert profiles[0].browser == "safari"
        assert profiles[0].profile_name == "Default"


def test_get_cookies_returns_list() -> None:
    """get_cookies should return a list of cookies."""
    cookies = get_cookies()
    assert isinstance(cookies, list)


def test_get_cookies_filters_by_domain() -> None:
    """get_cookies should filter by domain when specified."""
    cookies = get_cookies(domain="apple.com")
    for cookie in cookies:
        assert "apple" in cookie.domain.lower()
