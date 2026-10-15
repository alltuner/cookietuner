# ABOUTME: Tests for capturing cookies from a throwaway Chrome sign-in
# ABOUTME: Drives real Chrome against a local server, so no browser state is mocked

import asyncio
import http.server
import os
import signal
import socketserver
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cookietuner.capture import (
    EXTRA_ARGUMENTS_ENV,
    PROFILE_PREFIX,
    _BrowserGone,
    _wait_for_cookies,
    capture,
    capture_async,
    chrome_app_path,
    chrome_arguments,
    to_cookie,
)
from cookietuner.conditions import Conditions, Progress, build, join_chunks
from cookietuner.errors import CaptureIncomplete, CaptureTimeout
from cookietuner.models import Cookie

PAGE = b"<html><body>signed in</body></html>"
# Stands in for a person closing the window once they've signed in. The delay
# is well past one poll, so the test checks the close signal, not the race
# between a cookie being set and the window vanishing.
SELF_CLOSING_PAGE = (
    b"<html><body><script>setTimeout(window.close, 1500)</script></body></html>"
)

# A cookie too big for one header, split the way Supabase's SSR helpers do it.
CHUNKED = "sb-test-auth-token"

# Stands in for someone filling the form in and submitting it.
LOGIN_PAGE = """<html><body>
<form id="signin" method="post" action="/signin">
  <input name="who" value="someone">
</form>
<script>
  setTimeout(() => document.getElementById("signin").submit(), 300);
</script>
</body></html>""".encode()

# The trailing chunk lands well after the sign-in conditions first hold, so
# only a capture that settles sees it.
TRAILING_CHUNK_DELAY_MS = 1200
DASHBOARD_PAGE = f"""<html><body>dashboard
<script>
  setTimeout(
    () => document.cookie = "{CHUNKED}.1=second; Path=/",
    {TRAILING_CHUNK_DELAY_MS},
  );
</script>
</body></html>""".encode()


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


class _SignInHandler(_Handler):
    """A sign-in in the shape real ones come in.

    The name that means "signed in" is set for anonymous visitors too, the real
    session arrives only after a form post, its token is split across chunks,
    and the last chunk turns up after the redirect to the dashboard.
    """

    def do_GET(self) -> None:
        if self.path.startswith("/dashboard"):
            self._page(DASHBOARD_PAGE)
        elif self.path in ("/", "/login"):
            # Deliberately the same name the signed-in session uses, so a
            # capture waiting on the name alone would finish here.
            self._page(LOGIN_PAGE, ["uid=anon_7; Path=/"])
        else:
            # Anything else, Chrome's favicon request included, must not reset
            # the cookies this sign-in is about.
            self.send_error(404)

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(303)
        self.send_header("Location", "/dashboard")
        for cookie in (
            "uid=real_42; Path=/",
            "session_id=s3cr3t; Path=/; HttpOnly",
            f"{CHUNKED}.0=first; Path=/",
        ):
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _page(self, body: bytes, cookies: tuple[str, ...] | list[str] = ()) -> None:
        self.send_response(200)
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(handler: type[http.server.BaseHTTPRequestHandler]) -> Iterator[str]:
    """Serves one handler on a loopback port for the life of a test.

    Threaded, because Chrome opens several connections at once and a serial
    server would make it wait.
    """
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}/"
        server.shutdown()


@pytest.fixture
def login_url() -> Iterator[str]:
    """Serves a page that sets cookies, on a loopback port."""
    yield from _serve(_Handler)


@pytest.fixture
def self_closing_url() -> Iterator[str]:
    """Serves a page whose script closes the window shortly after load."""
    yield from _serve(_SelfClosingHandler)


@pytest.fixture
def sign_in_url() -> Iterator[str]:
    """Serves the anonymous-then-real sign-in, with chunks and a redirect."""
    yield from _serve(_SignInHandler)


def _leftover_profiles() -> list[Path]:
    return list(Path(tempfile.gettempdir()).glob(f"{PROFILE_PREFIX}*"))


@pytest.fixture
def no_leftover_profiles() -> Iterator[None]:
    """Fails the test if a capture leaves its temporary profile behind."""
    before = set(_leftover_profiles())
    yield
    assert set(_leftover_profiles()) - before == set()


_requires_chrome = pytest.mark.skipif(
    chrome_app_path() is None, reason="Google Chrome is not installed"
)


def drives_chrome(test: Callable[..., None]) -> Callable[..., None]:
    """Marks a test that opens a real Chrome window.

    Deselect these with ``-m "not browser"`` where no desktop session exists.
    """
    return pytest.mark.browser(_requires_chrome(test))


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


def raw_cookie(name: str, value: str = "v") -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "domain": "example.com",
        "path": "/",
        "expires": -1,
        "session": True,
    }


class _FakeBrowser:
    """Hands out scripted polls, then tears the session down.

    Only the DevTools transport is stood in for; the waiting, settling and
    browser-end logic under test is the real thing. Killing real Chrome covers
    that path too, but not deterministically enough to pin this behaviour on.
    """

    def __init__(
        self,
        polls: list[list[dict[str, Any]]],
        *,
        ends_after: int | None = None,
        closes_after: int | None = None,
    ) -> None:
        """Polls are served in order, the last one standing in for no change.

        ``ends_after`` is the poll the DevTools session dies on, as it does
        when Chrome quits. ``closes_after`` leaves Chrome running with no page
        left, as closing the last window does.
        """
        self._polls = polls
        self._ends_after = ends_after
        self._closes_after = closes_after
        self._taken = 0

    async def cookies(self) -> list[dict[str, Any]]:
        self._taken += 1
        if self._ends_after is not None and self._taken > self._ends_after:
            raise _BrowserGone("Chrome closed the DevTools pipe")
        return self._polls[min(self._taken, len(self._polls)) - 1]

    async def pages(self) -> list[str]:
        if self._closes_after is not None and self._taken > self._closes_after:
            return []
        return ["https://example.com/login"]


def wait_on(
    browser: _FakeBrowser,
    conditions: Conditions,
    settle: float = 0.0,
    on_progress: Callable[[list[str]], None] | None = None,
) -> list[Cookie]:
    progress = Progress(pending=conditions.describe())
    return asyncio.run(
        _wait_for_cookies(
            browser,  # type: ignore[arg-type]
            frozenset(),
            conditions,
            settle,
            on_progress,
            progress,
        )
    )


def test_a_browser_that_vanishes_mid_poll_answers_with_the_last_snapshot() -> None:
    """Quitting Chrome tears down the session the cookies are read from.

    The read for that poll fails, so the snapshot before it is the answer.
    Returning nothing instead would silently lose the whole sign-in.
    """
    browser = _FakeBrowser([[raw_cookie("session_id", "s3cr3t")]], ends_after=2)

    cookies = wait_on(browser, Conditions())

    assert [(c.name, c.value) for c in cookies] == [("session_id", "s3cr3t")]


def test_a_closed_window_answers_with_the_last_snapshot() -> None:
    """Closing the last window ends a capture that was given no conditions."""
    browser = _FakeBrowser([[raw_cookie("session_id")]], closes_after=1)

    cookies = wait_on(browser, Conditions())

    assert [c.name for c in cookies] == ["session_id"]


def test_a_browser_that_ends_before_the_conditions_hold_is_incomplete() -> None:
    conditions = build(until={"session_id"}, until_values=None, until_url=None)

    with pytest.raises(CaptureIncomplete) as caught:
        wait_on(_FakeBrowser([[raw_cookie("other")]], ends_after=2), conditions)

    assert "session_id" in str(caught.value)


def test_a_closed_window_before_the_conditions_hold_is_incomplete() -> None:
    """A partial session must never come back as if it were the real thing."""
    conditions = build(until={"session_id"}, until_values=None, until_url=None)

    with pytest.raises(CaptureIncomplete):
        wait_on(_FakeBrowser([[raw_cookie("other")]], closes_after=1), conditions)


def test_a_browser_that_ends_while_settling_keeps_what_it_had() -> None:
    """The conditions did hold, so the sign-in is done however the browser ends."""
    browser = _FakeBrowser([[raw_cookie("session_id")]], ends_after=2)
    conditions = build(until={"session_id"}, until_values=None, until_url=None)

    cookies = wait_on(browser, conditions, settle=30)

    assert [c.name for c in cookies] == ["session_id"]


def test_settling_waits_for_a_cookie_that_arrives_late() -> None:
    first = [raw_cookie("auth-token.0", "first")]
    both = [raw_cookie("auth-token.0", "first"), raw_cookie("auth-token.1", "second")]
    conditions = build(until={"auth-token"}, until_values=None, until_url=None)

    without_settling = wait_on(_FakeBrowser([first, both]), conditions)
    settled = wait_on(_FakeBrowser([first, both]), conditions, settle=0.6)

    assert [c.name for c in without_settling] == ["auth-token.0"]
    assert join_chunks(settled, "auth-token") == "firstsecond"


def test_progress_is_reported_only_when_it_changes() -> None:
    reported: list[list[str]] = []
    browser = _FakeBrowser(
        [[raw_cookie("other")], [raw_cookie("other")], [raw_cookie("session_id")]]
    )
    conditions = build(until={"session_id"}, until_values=None, until_url=None)

    wait_on(browser, conditions, on_progress=reported.append)

    assert reported == [[]]


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_returns_the_cookies_it_was_told_to_wait_for(login_url: str) -> None:
    """Capture should see HttpOnly and session cookies a store reader can't."""
    cookies = capture(
        url=login_url,
        domains={"127.0.0.1"},
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


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_only_returns_the_requested_domain(login_url: str) -> None:
    cookies = capture(
        url=login_url, domains={"127.0.0.1"}, until={"session_id"}, timeout=60
    )
    assert cookies
    assert {c.domain for c in cookies} == {"127.0.0.1"}


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_times_out_naming_the_cookies_that_never_arrived(
    login_url: str,
) -> None:
    with pytest.raises(CaptureTimeout) as caught:
        capture(url=login_url, domains={"127.0.0.1"}, until={"never_set"}, timeout=8)

    message = str(caught.value)
    assert "never_set" in message
    assert "s3cr3t" not in message


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_names_the_domain_a_wanted_cookie_turned_up_on(
    login_url: str,
) -> None:
    """Exact domain matching is the likeliest reason for a fruitless wait."""
    with pytest.raises(CaptureTimeout) as caught:
        capture(url=login_url, domains={"localhost"}, until={"session_id"}, timeout=8)

    message = str(caught.value)
    assert "127.0.0.1" in message
    assert "s3cr3t" not in message


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_returns_everything_for_the_domain_when_the_window_closes(
    self_closing_url: str,
) -> None:
    """Without conditions, closing the window is the signal that sign-in is done."""
    cookies = capture(url=self_closing_url, domains={"127.0.0.1"}, timeout=60)
    assert {c.name for c in cookies} == {"session_id", "csrf_token"}


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_reports_a_window_closed_before_the_cookies_appeared(
    self_closing_url: str,
) -> None:
    with pytest.raises(CaptureIncomplete) as caught:
        capture(
            url=self_closing_url, domains={"127.0.0.1"}, until={"never_set"}, timeout=60
        )

    assert "never_set" in str(caught.value)


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_waits_out_an_anonymous_session_and_collects_the_real_one(
    sign_in_url: str,
) -> None:
    """The whole point, against a sign-in shaped like the awkward real ones.

    The name is set for anonymous visitors, so only the value condition can
    tell the sign-in happened; the token is chunked; and the last chunk lands
    after the redirect, so only a settling capture sees it.
    """
    cookies = capture(
        url=sign_in_url,
        domains={"127.0.0.1"},
        until={CHUNKED},
        until_values=["uid!=anon_*"],
        until_url="*/dashboard*",
        settle=3,
        timeout=60,
    )

    by_name = {c.name: c for c in cookies}
    assert by_name["uid"].value == "real_42"
    assert by_name["session_id"].is_httponly is True
    assert join_chunks(cookies, CHUNKED) == "firstsecond"


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_capture_without_settling_can_miss_the_trailing_chunk(
    sign_in_url: str,
) -> None:
    """Why --settle exists: a chunk set looks complete as soon as it has .0."""
    cookies = capture(
        url=sign_in_url,
        domains={"127.0.0.1"},
        until={CHUNKED},
        until_values=["uid!=anon_*"],
        until_url="*/dashboard*",
        timeout=60,
    )

    assert {c.name for c in cookies} >= {"uid", f"{CHUNKED}.0"}
    assert f"{CHUNKED}.1" not in {c.name for c in cookies}


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
def test_a_name_only_condition_would_end_on_the_anonymous_cookie(
    sign_in_url: str,
) -> None:
    """The problem the value condition solves, pinned down.

    Waiting for the name alone finishes while the visitor is still anonymous.
    """
    cookies = capture(url=sign_in_url, domains={"127.0.0.1"}, until={"uid"}, timeout=60)

    assert {c.name: c.value for c in cookies}["uid"] == "anon_7"


def _capture_chrome_pid() -> int | None:
    """The browser process of a running capture, not one of its helpers.

    Matched on the temporary profile's name, so an everyday Chrome and any
    other capture are left alone.
    """
    found = subprocess.run(
        ["pgrep", "-f", PROFILE_PREFIX], capture_output=True, text=True
    )
    for pid in found.stdout.split():
        command = subprocess.run(
            ["ps", "-o", "command=", "-p", pid], capture_output=True, text=True
        ).stdout
        if PROFILE_PREFIX in command and "--type=" not in command:
            return int(pid)
    return None


async def _capture_until_signalled(
    url: str, how: signal.Signals, **kwargs: Any
) -> list[Cookie]:
    """Signals the capture's own Chrome once it has what it was waiting for.

    Stands in for Cmd+Q (SIGTERM) and for Chrome dying outright (SIGKILL),
    neither of which closes a window first.
    """
    ready = asyncio.Event()

    def watch(pending: list[str]) -> None:
        if not pending:
            ready.set()

    async def end_the_browser() -> None:
        await ready.wait()
        pid = _capture_chrome_pid()
        assert pid is not None, "no capture Chrome to signal"
        os.kill(pid, how)

    ender = asyncio.create_task(end_the_browser())
    try:
        return await capture_async(url=url, on_progress=watch, **kwargs)
    finally:
        ender.cancel()


@drives_chrome
@pytest.mark.usefixtures("no_leftover_profiles")
@pytest.mark.parametrize("how", [signal.SIGTERM, signal.SIGKILL])
def test_a_browser_ended_without_closing_keeps_the_sign_in(
    login_url: str, how: signal.Signals
) -> None:
    """Quitting Chrome has to mean what closing its window means.

    A long settle keeps the capture running until the signal lands, so the
    answer can only have come from the snapshot taken before Chrome went.
    """
    cookies = asyncio.run(
        _capture_until_signalled(
            login_url,
            how,
            domains={"127.0.0.1"},
            until={"session_id"},
            settle=30,
            timeout=60,
        )
    )

    assert {c.name: c.value for c in cookies}["session_id"] == "s3cr3t"


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


def test_no_unsupported_flag_warning_covers_the_sign_in_page() -> None:
    """Chrome bars the blink flag as unsupported; the warning must not show."""
    args = chrome_arguments(
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        profile=Path("/tmp/profile"),
        url="https://example.com/login",
        proxy=None,
    )
    assert "--test-type" in args


def test_extra_switches_are_passed_before_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chrome takes the URL positionally, so anything added has to precede it."""
    monkeypatch.setenv(EXTRA_ARGUMENTS_ENV, "--headless=new --window-size=800,600")

    args = chrome_arguments(
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        profile=Path("/tmp/profile"),
        url="https://example.com/login",
        proxy=None,
    )

    assert args[-1] == "https://example.com/login"
    assert "--headless=new" in args
    assert "--window-size=800,600" in args


def test_no_extra_switches_by_default() -> None:
    """A capture needs a window someone can sign in to, so nothing is added."""
    args = chrome_arguments(
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        profile=Path("/tmp/profile"),
        url="https://example.com/login",
        proxy=None,
    )

    assert not [a for a in args if "headless" in a]


def test_the_blocking_and_async_captures_take_the_same_arguments() -> None:
    """One is a wrapper around the other, so a new option can't reach only one."""
    import inspect

    assert inspect.signature(capture).parameters == (
        inspect.signature(capture_async).parameters
    )


def test_a_malformed_condition_is_refused_before_chrome_starts() -> None:
    """Checked up front, so a typo doesn't cost a sign-in."""
    with pytest.raises(ValueError, match="name=pattern"):
        capture(url="https://example.com/login", until_values=["nonsense"])

    with pytest.raises(ValueError, match="until takes a set"):
        capture(url="https://example.com/login", until="session_id")
