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

from .chrome import CHROME_BASE_PATH
from .domain import domain_matches
from .errors import (
    BrowserClosedEarly,
    CaptureTimeout,
    ChromeNotFound,
    PasswordsExtensionMissing,
)
from .models import Cookie

PROFILE_PREFIX = "cookietuner-capture-"

# Apple's iCloud Passwords extension, which reaches the Passwords app through a
# native helper. The helper only talks to these two extension IDs, and Chrome
# derives an ID from the SHA256 of the extension's public key, so this key is
# fixed for this ID and a copy loaded from disk has to carry it to be accepted.
PASSWORDS_EXTENSION_ID = "pejdijmoenmkgeppbflobdenhhabjlaj"
PASSWORDS_EXTENSION_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAk4xPYZla5XqlDN0PPiLCQAYRqdaR"
    "06jSl3sntEE5jHoe7XldFqhsdBSp4L8mozwjCwi6z5YtEpTV1L2k4WYmDuiwoH7YKGlQD/Yb"
    "C8QMcPvGLWOr8WYfXWtECKv0Nx7Tahk8nCIDWgJVm8YmPIDhPv4o5VVrq6aUveCKvTOskHWF"
    "yRzSTC2VKpzIVX7F65UzqqOmqLfMpo6lfaLcKSC7G6oQLA/wS7hcGZEwZ11si6XWR4o/hDuU"
    "St6zdacy/sc7H80eH3lMnEmvb6HoB7+KvxfGIU7dqRmhA/w/X0qkiIJYeoo4tZrNxBj7TTLz"
    "9hnHUbMRwJqsoIU+pkoprgFWDQIDAQAB"
)

CHROME_APP_PATHS = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

# How often we ask the browser for its cookies and its open windows.
POLL_INTERVAL = 0.25

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


def passwords_extension_source(profile_name: str = "Default") -> Path | None:
    """Finds the newest installed copy of Apple's iCloud Passwords extension.

    A fresh profile has no extensions, so the files are taken from the Chrome
    profile where the person already installed it.
    """
    versions = CHROME_BASE_PATH / profile_name / "Extensions" / PASSWORDS_EXTENSION_ID
    try:
        installed = sorted(
            p for p in versions.iterdir() if (p / "manifest.json").is_file()
        )
    except OSError:
        return None
    return installed[-1] if installed else None


def stage_passwords_extension(source: Path, into: Path) -> Path:
    """Copies the extension and puts its key back, so it keeps its store ID.

    Chrome computes an unpacked extension's ID from its path unless the manifest
    names a key, and the wrong ID means the native helper refuses to talk to it.

    Raises:
        PasswordsExtensionMissing: if there's no extension to copy.
    """
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise PasswordsExtensionMissing(
            f"No iCloud Passwords extension to copy from: {manifest_path}. "
            "Install it in Chrome first, or capture without --passwords."
        )

    shutil.copytree(source, into)
    staged_manifest = into / "manifest.json"
    manifest = json.loads(staged_manifest.read_text())
    manifest["key"] = PASSWORDS_EXTENSION_KEY
    staged_manifest.write_text(json.dumps(manifest))
    return into


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

    Chrome calls that an unsupported flag and puts a yellow "stability and
    security will suffer" bar over the page, which is alarming in a window
    someone is about to type a password into. ``--test-type`` drops the bar.
    It does not weaken certificate warnings: a self-signed site still hits the
    interstitial with it set.
    """
    args = [
        str(chrome),
        f"--user-data-dir={profile}",
        "--remote-debugging-pipe",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--test-type",
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

    def __init__(
        self, chrome: Path, profile: Path, url: str, proxy: str | None
    ) -> None:
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
        # Wrapped straight away so our ends are owned by a file object and get
        # closed even if the launch below fails.
        requests = os.fdopen(request_write, "wb", 0)
        replies = os.fdopen(reply_read, "rb", 0)

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
            lambda: asyncio.StreamReaderProtocol(reader), replies
        )
        # FlowControlMixin is what asyncio's own pipe wrappers use to turn a
        # transport into something StreamWriter can drain.
        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, requests
        )
        self._writer = asyncio.StreamWriter(transport, protocol, None, loop)

    async def _call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> Any:
        assert self._reader is not None and self._writer is not None
        self._next_id += 1
        request: dict[str, Any] = {"id": self._next_id, "method": method}
        if params:
            request["params"] = params
        if session:
            request["sessionId"] = session
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

    async def load_extension(self, path: Path) -> str:
        """Installs an unpacked extension and returns the ID Chrome gave it."""
        result = await self._call("Extensions.loadUnpacked", {"path": str(path)})
        return str(result["id"])

    async def navigate(self, url: str) -> None:
        """Points the open window at a URL.

        Used after loading an extension, so its content scripts run on the page
        the person signs in to rather than only on later navigations.
        """
        targets = await self._call("Target.getTargets")
        pages = [t for t in targets["targetInfos"] if t["type"] == "page"]
        if not pages:
            raise _BrowserGone("Chrome has no window to navigate")
        attached = await self._call(
            "Target.attachToTarget", {"targetId": pages[0]["targetId"], "flatten": True}
        )
        await self._call("Page.navigate", {"url": url}, session=attached["sessionId"])

    async def cookies(self) -> list[dict[str, Any]]:
        result = await self._call("Storage.getCookies")
        return list(result["cookies"])

    async def stop(self) -> None:
        """Quits Chrome and removes its profile, whatever went before.

        The profile is removed even if quitting fails or this is running in a
        task that has already been cancelled, because leaving a signed-in
        profile on disk defeats the point.
        """
        try:
            await self._quit()
        finally:
            shutil.rmtree(self._profile, ignore_errors=True)
            if self._profile.exists():
                shutil.rmtree(self._profile)

    async def _quit(self) -> None:
        """Asks Chrome to close, and kills it if it won't."""
        if self._process is None:
            return
        if self._process.returncode is None and self._writer is not None:
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
        finally:
            if self._writer is not None:
                self._writer.close()


def _missing(until: set[str], cookies: list[Cookie]) -> set[str]:
    return until - {cookie.name for cookie in cookies}


async def capture_async(
    *,
    url: str,
    domain: str | None = None,
    until: set[str] | None = None,
    timeout: float = 300.0,
    passwords: bool = False,
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
        passwords: Load Apple's iCloud Passwords extension, so signing in can
                   use the Passwords app instead of typing. The profile is new
                   every time, so expect the extension's pairing step on every
                   capture.
        proxy: Proxy for the browser's traffic, e.g. ``socks5://host:1080``.

    Returns:
        The cookies in effect when the wait finished, including HttpOnly and
        session cookies that never reach disk.

    Raises:
        ChromeNotFound: if Google Chrome isn't installed.
        CaptureTimeout: if ``timeout`` passes before the cookies appear.
        BrowserClosedEarly: if the browser quits before they do.
        PasswordsExtensionMissing: if ``passwords`` is set and the extension
                                   isn't installed to copy from.
    """
    chrome = chrome_app_path()
    if chrome is None:
        raise ChromeNotFound(
            "Google Chrome is not installed; looked in "
            + " and ".join(str(p) for p in CHROME_APP_PATHS)
        )

    extension_source = None
    if passwords:
        extension_source = passwords_extension_source()
        if extension_source is None:
            raise PasswordsExtensionMissing(
                "No iCloud Passwords extension found in Chrome's Default "
                "profile. Install it in Chrome first, or capture without it."
            )

    wanted = set(until or ())
    profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))
    staging = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX)) if passwords else None
    # With the extension, the window opens blank and navigates once it's in, so
    # its content scripts run on the sign-in page itself.
    browser = _Chrome(chrome, profile, "about:blank" if passwords else url, proxy)
    other_domains: dict[str, set[str]] = {}

    try:
        await browser.start()
        if extension_source is not None and staging is not None:
            await browser.load_extension(
                stage_passwords_extension(extension_source, staging / "extension")
            )
            await browser.navigate(url)
        try:
            async with asyncio.timeout(timeout):
                return await _wait_for_cookies(browser, domain, wanted, other_domains)
        except TimeoutError as exc:
            waited_for = ", ".join(sorted(wanted)) if wanted else "the window to close"
            raise CaptureTimeout(
                f"Timed out after {timeout:g}s waiting for {waited_for}"
                + _elsewhere(wanted, other_domains)
            ) from exc
    finally:
        try:
            await browser.stop()
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)


def _elsewhere(wanted: set[str], other_domains: dict[str, set[str]]) -> str:
    """Points at cookies that did arrive, but on a domain that wasn't asked for.

    Domains don't match by subdomain, so asking for ``example.com`` when the
    cookie lands on ``www.example.com`` otherwise just waits out the clock.
    """
    sightings = [
        f"{name} on {', '.join(sorted(other_domains[name]))}"
        for name in sorted(wanted)
        if other_domains.get(name)
    ]
    if not sightings:
        return ""
    return (
        ". Did turn up, on a domain you didn't ask for: "
        + "; ".join(sightings)
        + " (domains match exactly, so subdomains need naming in full)"
    )


async def _wait_for_cookies(
    browser: _Chrome,
    domain: str | None,
    wanted: set[str],
    other_domains: dict[str, set[str]],
) -> list[Cookie]:
    """Polls the browser until the wanted cookies exist or the window closes.

    Closing the last window makes Chrome tear down the session, and its cookies
    stop being readable, so each pass takes a snapshot and only then checks
    whether the window is still there. That leaves the last snapshot as the
    answer, taken as late as it can be.

    Wanted cookies seen on some other domain are recorded in ``other_domains``,
    so a fruitless wait can say where they went.
    """
    found: list[Cookie] = []
    seen_a_window = False

    while True:
        try:
            found = []
            for cookie in (to_cookie(raw) for raw in await browser.cookies()):
                if domain is None or domain_matches(cookie.domain, domain):
                    found.append(cookie)
                elif cookie.name in wanted:
                    other_domains.setdefault(cookie.name, set()).add(cookie.domain)

            if wanted and not _missing(wanted, found):
                return found

            if await browser.open_page_count():
                seen_a_window = True
            elif seen_a_window:
                return _finish_on_close(found, wanted, other_domains)
        except _BrowserGone as exc:
            if seen_a_window:
                return _finish_on_close(found, wanted, other_domains)
            raise BrowserClosedEarly(f"Chrome quit before signing in: {exc}") from exc

        await asyncio.sleep(POLL_INTERVAL)


def _finish_on_close(
    found: list[Cookie], wanted: set[str], other_domains: dict[str, set[str]]
) -> list[Cookie]:
    """Decides what a closed window means: done, or gone too early."""
    missing = _missing(wanted, found)
    if missing:
        raise BrowserClosedEarly(
            "The browser closed before these cookies were set: "
            + ", ".join(sorted(missing))
            + _elsewhere(missing, other_domains)
        )
    return found


def capture(
    *,
    url: str,
    domain: str | None = None,
    until: set[str] | None = None,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
) -> list[Cookie]:
    """Blocking version of :func:`capture_async`, for scripts."""
    return asyncio.run(
        capture_async(
            url=url,
            domain=domain,
            until=until,
            timeout=timeout,
            passwords=passwords,
            proxy=proxy,
        )
    )
