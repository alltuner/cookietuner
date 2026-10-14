# ABOUTME: Tests for capturing cookies from a throwaway Chrome sign-in
# ABOUTME: Drives real Chrome against a local server, so no browser state is mocked

import http.server
import socketserver
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from cookietuner.capture import (
    PROFILE_PREFIX,
    capture,
    chrome_app_path,
    chrome_arguments,
    to_cookie,
)
from cookietuner.errors import BrowserClosedEarly, CaptureTimeout

PAGE = b"<html><body>signed in</body></html>"
# Stands in for a person closing the window once they've signed in. The delay
# is well past one poll, so the test checks the close signal, not the race
# between a cookie being set and the window vanishing.
SELF_CLOSING_PAGE = (
    b"<html><body><script>setTimeout(window.close, 1500)</script></body></html>"
)


class _Handler(http.server.BaseHTTPRequestHandler):
    """Sets one HttpOnly session cookie and one persistent cookie."""

    body = PAGE

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Set-Cookie", "session_id=s3cr3t; Path=/; HttpOnly")
        self.send_header("Set-Cookie", "csrf_token=tok3n; Path=/; Max-Age=3600")
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _SelfClosingHandler(_Handler):
    body = SELF_CLOSING_PAGE


@pytest.fixture
def login_url() -> Iterator[str]:
    """Serves a page that sets cookies, on a loopback port."""
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}/"
        server.shutdown()


@pytest.fixture
def self_closing_url() -> Iterator[str]:
    """Serves a page whose script closes the window shortly after load."""
    with socketserver.TCPServer(("127.0.0.1", 0), _SelfClosingHandler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}/"
        server.shutdown()


def _leftover_profiles() -> list[Path]:
    return list(Path(tempfile.gettempdir()).glob(f"{PROFILE_PREFIX}*"))


@pytest.fixture
def no_leftover_profiles() -> Iterator[None]:
    """Fails the test if a capture leaves its temporary profile behind."""
    before = set(_leftover_profiles())
    yield
    assert set(_leftover_profiles()) - before == set()


requires_chrome = pytest.mark.skipif(
    chrome_app_path() is None, reason="Google Chrome is not installed"
)


def test_to_cookie_treats_a_session_cookie_as_never_expiring() -> None:
    cookie = to_cookie(
        {
            "name": "session_id",
            "value": "s3cr3t",
            "domain": "example.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "session": True,
        }
    )
    assert cookie.expires is None
    assert cookie.is_httponly is True
    assert cookie.is_secure is True
    assert cookie.same_site is None


def test_to_cookie_reads_expiry_and_samesite() -> None:
    cookie = to_cookie(
        {
            "name": "csrf_token",
            "value": "tok3n",
            "domain": ".example.com",
            "path": "/app",
            "expires": 1_792_021_080,
            "httpOnly": False,
            "secure": False,
            "session": False,
            "sameSite": "Lax",
        }
    )
    assert cookie.expires is not None
    assert cookie.expires.year == 2026
    assert cookie.same_site == "lax"
    assert cookie.path == "/app"
    assert cookie.domain == ".example.com"


@requires_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_returns_the_cookies_it_was_told_to_wait_for(login_url: str) -> None:
    """Capture should see HttpOnly and session cookies a store reader can't."""
    cookies = capture(
        url=login_url,
        domain="127.0.0.1",
        until={"session_id", "csrf_token"},
        timeout=60,
    )

    by_name = {c.name: c for c in cookies}
    assert by_name.keys() >= {"session_id", "csrf_token"}
    assert by_name["session_id"].value == "s3cr3t"
    assert by_name["session_id"].is_httponly is True
    assert by_name["session_id"].expires is None
    assert by_name["csrf_token"].value == "tok3n"
    assert by_name["csrf_token"].expires is not None


@requires_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_only_returns_the_requested_domain(login_url: str) -> None:
    cookies = capture(
        url=login_url, domain="127.0.0.1", until={"session_id"}, timeout=60
    )
    assert cookies
    assert {c.domain for c in cookies} == {"127.0.0.1"}


@requires_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_times_out_naming_the_cookies_that_never_arrived(
    login_url: str,
) -> None:
    with pytest.raises(CaptureTimeout) as caught:
        capture(url=login_url, domain="127.0.0.1", until={"never_set"}, timeout=8)

    message = str(caught.value)
    assert "never_set" in message
    assert "s3cr3t" not in message


@requires_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_names_the_domain_a_wanted_cookie_turned_up_on(
    login_url: str,
) -> None:
    """Exact domain matching is the likeliest reason for a fruitless wait."""
    with pytest.raises(CaptureTimeout) as caught:
        capture(url=login_url, domain="localhost", until={"session_id"}, timeout=8)

    message = str(caught.value)
    assert "127.0.0.1" in message
    assert "s3cr3t" not in message


@requires_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_returns_everything_for_the_domain_when_the_window_closes(
    self_closing_url: str,
) -> None:
    """Without --until, closing the window is the signal that sign-in is done."""
    cookies = capture(url=self_closing_url, domain="127.0.0.1", timeout=60)
    assert {c.name for c in cookies} == {"session_id", "csrf_token"}


@requires_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_reports_a_window_closed_before_the_cookies_appeared(
    self_closing_url: str,
) -> None:
    with pytest.raises(BrowserClosedEarly) as caught:
        capture(
            url=self_closing_url, domain="127.0.0.1", until={"never_set"}, timeout=60
        )

    assert "never_set" in str(caught.value)


def test_chrome_app_path_is_the_installed_browser() -> None:
    path = chrome_app_path()
    if path is None:
        pytest.skip("Google Chrome is not installed")
    assert path.exists()
    assert path.name == "Google Chrome"


def test_proxy_adds_the_webrtc_guard_to_the_command_line() -> None:
    """A proxied session shouldn't leak the local address over WebRTC."""
    args = chrome_arguments(
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        profile=Path("/tmp/profile"),
        url="https://example.com/login",
        proxy="socks5://127.0.0.1:1080",
    )
    assert "--proxy-server=socks5://127.0.0.1:1080" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args


def test_without_a_proxy_no_proxy_switches_are_passed() -> None:
    args = chrome_arguments(
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        profile=Path("/tmp/profile"),
        url="https://example.com/login",
        proxy=None,
    )
    assert not [a for a in args if "proxy" in a or "webrtc" in a]


def test_the_browser_is_not_flagged_as_automated() -> None:
    """Sites should see an ordinary browser, so the sign-in isn't blocked."""
    args = chrome_arguments(
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        profile=Path("/tmp/profile"),
        url="https://example.com/login",
        proxy=None,
    )
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--enable-automation" not in args
