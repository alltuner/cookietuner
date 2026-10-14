# ABOUTME: Captures cookies from a throwaway Chrome window a person signs in to
# ABOUTME: Drives Chrome over the DevTools pipe, then deletes the temporary profile

import asyncio
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain import domain_matches
from .errors import BrowserClosedEarly, CaptureTimeout, ChromeNotFound
from .models import Cookie

PROFILE_PREFIX = "cookietuner-capture-"

CHROME_APP_PATHS = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

# How often we ask the browser for its cookies and its open windows.
POLL_INTERVAL = 0.5

# Chrome's cookie list for a whole profile can exceed asyncio's default 64 KiB.
PIPE_READ_LIMIT = 16 * 1024 * 1024

# How long to wait for Chrome to quit on its own before killing it.
SHUTDOWN_GRACE = 10.0


def chrome_app_path() -> Path | None:
    """Returns the installed Google Chrome binary, or None if it isn't there."""
    for path in CHROME_APP_PATHS:
        if path.exists():
            return path
    return None


def chrome_arguments(
    *,
    chrome: Path,
    profile: Path,
    url: str,
    proxy: str | None,
) -> list[str]:
    """Builds the command line for a throwaway, non-automated Chrome window.

    The DevTools pipe alone makes ``navigator.webdriver`` true, which some
    sign-in pages reject, so blink's AutomationControlled feature is turned
    off to leave an ordinary browser.
    """
    args = [
        str(chrome),
        f"--user-data-dir={profile}",
        "--remote-debugging-pipe",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ]
    if proxy:
        args.append(f"--proxy-server={proxy}")
        # Without this, WebRTC can reach the network directly and expose the
        # local address the proxy is there to hide.
        args.append("--force-webrtc-ip-handling-policy=disable_non_proxied_udp")
    args.append(url)
    return args


def to_cookie(raw: dict[str, Any]) -> Cookie:
    """Converts one DevTools cookie into cookietuner's model."""
    expires = raw.get("expires", -1)
    same_site = raw.get("sameSite")
    return Cookie(
        domain=raw["domain"],
        name=raw["name"],
        value=raw["value"],
        path=raw["path"],
        expires=(
            None
            if raw.get("session") or expires is None or expires < 0
            else datetime.fromtimestamp(expires, tz=timezone.utc)
        ),
        is_secure=bool(raw.get("secure")),
        is_httponly=bool(raw.get("httpOnly")),
        same_site=same_site.lower() if same_site else None,
    )


class _BrowserGone(Exception):
    """Chrome tore down the session we were reading cookies from."""


class _Chrome:
    """A throwaway Chrome window, driven over the DevTools pipe.

    Chrome reads requests on file descriptor 3 and writes replies on 4, each
    message a NUL-terminated JSON object.
    """

    def __init__(self, chrome: Path, profile: Path, url: str, proxy: str | None):
        self._chrome = chrome
        self._profile = profile
        self._url = url
        self._proxy = proxy
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 0

    async def start(self) -> None:
        request_read, request_write = os.pipe()
        reply_read, reply_write = os.pipe()

        # pass_fds keeps the descriptor numbers but can't choose them, so a
        # shell moves them onto the 3 and 4 Chrome expects. Leaving the
        # originals open alongside is harmless: they are the same pipe ends.
        launcher = [
            "/bin/sh",
            "-c",
            f'exec 3<&{request_read} 4>&{reply_write} "$@"',
            "chrome",
            *chrome_arguments(
                chrome=self._chrome,
                profile=self._profile,
                url=self._url,
                proxy=self._proxy,
            ),
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *launcher,
                pass_fds=(request_read, reply_write),
                # Chrome's own logging would otherwise land in piped output.
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        finally:
            os.close(request_read)
            os.close(reply_write)

        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(limit=PIPE_READ_LIMIT)
        self._reader = reader
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader),
            os.fdopen(reply_read, "rb", 0),
        )
        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin,
            os.fdopen(request_write, "wb", 0),
        )
        self._writer = asyncio.StreamWriter(transport, protocol, None, loop)

    async def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        assert self._reader is not None and self._writer is not None
        self._next_id += 1
        request: dict[str, Any] = {"id": self._next_id, "method": method}
        if params:
            request["params"] = params
        self._writer.write(json.dumps(request).encode() + b"\0")
        await self._writer.drain()

        while True:
            try:
                raw = await self._reader.readuntil(b"\0")
            except (asyncio.IncompleteReadError, BrokenPipeError) as exc:
                raise _BrowserGone("Chrome closed the DevTools pipe") from exc
            message = json.loads(raw[:-1])
            if message.get("id") != self._next_id:
                continue  # An event, or a reply we no longer wait for.
            if "error" in message:
                raise _BrowserGone(message["error"].get("message", method))
            return message["result"]

    async def open_page_count(self) -> int:
        targets = await self._call("Target.getTargets")
        return sum(1 for t in targets["targetInfos"] if t["type"] == "page")

    async def cookies(self) -> list[dict[str, Any]]:
        result = await self._call("Storage.getCookies")
        return list(result["cookies"])

    async def stop(self) -> None:
        """Quits Chrome and removes its profile, whatever went before."""
        if self._process is not None:
            if self._process.returncode is None:
                try:
                    await self._call("Browser.close")
                except (_BrowserGone, OSError):
                    pass
            try:
                async with asyncio.timeout(SHUTDOWN_GRACE):
                    await self._process.wait()
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        if self._writer is not None:
            self._writer.close()
        shutil.rmtree(self._profile, ignore_errors=True)
        if self._profile.exists():
            # Leaving a signed-in profile on disk defeats the point.
            shutil.rmtree(self._profile)


def _missing(until: set[str], cookies: list[Cookie]) -> set[str]:
    return until - {cookie.name for cookie in cookies}


async def capture_async(
    *,
    url: str,
    domain: str | None = None,
    until: set[str] | None = None,
    timeout: float = 300.0,
    proxy: str | None = None,
) -> list[Cookie]:
    """Opens a throwaway Chrome window and returns the cookies a sign-in sets.

    The browser starts on a fresh profile with no history or logins, loads
    ``url`` and waits for the person to sign in by hand. cookietuner never
    types, fills or reads credentials.

    Args:
        url: Page to open, usually a sign-in form.
        domain: Only return cookies set for exactly this domain, matched the
                same way as ``cookies`` (a leading dot is ignored, subdomains
                don't match).
        until: Cookie names to wait for. Without them, the capture finishes
               when the last window closes.
        timeout: Seconds to wait before giving up.
        proxy: Proxy for the browser's traffic, e.g. ``socks5://host:1080``.

    Returns:
        The cookies in effect when the wait finished, including HttpOnly and
        session cookies that never reach disk.

    Raises:
        ChromeNotFound: if Google Chrome isn't installed.
        CaptureTimeout: if ``timeout`` passes before the cookies appear.
        BrowserClosedEarly: if the browser quits before they do.
    """
    chrome = chrome_app_path()
    if chrome is None:
        raise ChromeNotFound(
            "Google Chrome is not installed; looked in "
            + " and ".join(str(p) for p in CHROME_APP_PATHS)
        )

    wanted = set(until or ())
    profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))
    browser = _Chrome(chrome, profile, url, proxy)

    try:
        await browser.start()
        try:
            async with asyncio.timeout(timeout):
                return await _wait_for_cookies(browser, domain, wanted)
        except TimeoutError as exc:
            waited_for = ", ".join(sorted(wanted)) if wanted else "the window to close"
            raise CaptureTimeout(
                f"Timed out after {timeout:g}s waiting for {waited_for}"
            ) from exc
    finally:
        await browser.stop()


async def _wait_for_cookies(
    browser: _Chrome, domain: str | None, wanted: set[str]
) -> list[Cookie]:
    """Polls the browser until the wanted cookies exist or the window closes."""
    found: list[Cookie] = []
    seen_a_window = False

    while True:
        try:
            pages = await browser.open_page_count()
            if pages:
                seen_a_window = True
            elif seen_a_window:
                return _finish_on_close(found, wanted)

            found = [
                cookie
                for cookie in (to_cookie(raw) for raw in await browser.cookies())
                if domain is None or domain_matches(cookie.domain, domain)
            ]
        except _BrowserGone as exc:
            if seen_a_window:
                return _finish_on_close(found, wanted)
            raise BrowserClosedEarly(f"Chrome quit before signing in: {exc}") from exc

        if wanted and not _missing(wanted, found):
            return found

        await asyncio.sleep(POLL_INTERVAL)


def _finish_on_close(found: list[Cookie], wanted: set[str]) -> list[Cookie]:
    """Decides what a closed window means: done, or gone too early."""
    missing = _missing(wanted, found)
    if missing:
        raise BrowserClosedEarly(
            "The browser closed before these cookies were set: "
            + ", ".join(sorted(missing))
        )
    return found


def capture(
    *,
    url: str,
    domain: str | None = None,
    until: set[str] | None = None,
    timeout: float = 300.0,
    proxy: str | None = None,
) -> list[Cookie]:
    """Blocking version of :func:`capture_async`, for scripts."""
    return asyncio.run(
        capture_async(url=url, domain=domain, until=until, timeout=timeout, proxy=proxy)
    )
