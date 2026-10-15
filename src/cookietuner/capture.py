# ABOUTME: Captures cookies from a throwaway Chrome window a person signs in to
# ABOUTME: Drives Chrome over the DevTools pipe, then deletes the temporary profile

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from . import conditions
from .chrome import CHROME_BASE_PATH
from .conditions import PAGE_SCHEMES, Conditions, Progress
from .domain import domain_matches
from .errors import (
    CaptureIncomplete,
    CaptureTimeout,
    ChromeNotFound,
    PasswordsExtensionMissing,
    ProfileAccessDenied,
)
from .identity import (
    IDENTITY_SCRIPT,
    accept_language,
    client_hints,
    high_entropy_hints,
)
from .models import CapturedSession, Cookie

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

# How long to wait for the open page to be able to say what the browser is. A
# page that never gets that far leaves the sign-in to carry on without hints.
IDENTITY_GRACE = 15.0


def chrome_app_path() -> Path | None:
    """Returns the installed Google Chrome binary, or None if it isn't there."""
    for path in CHROME_APP_PATHS:
        if path.exists():
            return path
    return None


def _profile_access_denied(path: Path, exc: OSError) -> ProfileAccessDenied:
    """Builds the error for a profile folder macOS won't let us read."""
    return ProfileAccessDenied(
        f"Chrome's profile folder is unreadable: {path}: {exc.strerror or exc}. "
        "macOS withholds it until the program running cookietuner has Full "
        "Disk Access: grant it in System Settings > Privacy & Security > Full "
        "Disk Access, to the terminal or app cookietuner runs under. Capturing "
        "without --passwords needs no access to the folder at all."
    )


def _has_manifest(version: Path) -> bool:
    """True if this extension version folder holds a manifest.

    ``Path.is_file`` answers False when macOS denies the question, which would
    make a denial look like a missing extension, so this asks in a way that
    tells the two apart.

    Raises:
        ProfileAccessDenied: if the manifest can't be reached.
    """
    try:
        (version / "manifest.json").stat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _profile_access_denied(version / "manifest.json", exc) from exc
    return True


def passwords_extension_source(profile_name: str = "Default") -> Path | None:
    """Finds the newest installed copy of Apple's iCloud Passwords extension.

    A fresh profile has no extensions, so the files are taken from the Chrome
    profile where the person already installed it.

    Returns:
        The extension's folder, or None if it isn't installed.

    Raises:
        ProfileAccessDenied: if Chrome's profile folder can't be read, which is
                             a different problem from the extension not being
                             installed.
    """
    profile = CHROME_BASE_PATH / profile_name
    versions = profile / "Extensions" / PASSWORDS_EXTENSION_ID
    try:
        installed = sorted(p for p in versions.iterdir() if _has_manifest(p))
    except FileNotFoundError:
        _require_readable(profile)
        return None
    except OSError as exc:
        raise _profile_access_denied(versions, exc) from exc
    return installed[-1] if installed else None


def _require_readable(profile: Path) -> None:
    """Tells a profile that isn't there from one macOS won't let us read.

    Raises:
        ProfileAccessDenied: if the folder exists but can't be listed.
    """
    try:
        next(iter(profile.iterdir()), None)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise _profile_access_denied(profile, exc) from exc


def stage_passwords_extension(source: Path, into: Path) -> Path:
    """Copies the extension and puts its key back, so it keeps its store ID.

    Chrome computes an unpacked extension's ID from its path unless the manifest
    names a key, and the wrong ID means the native helper refuses to talk to it.

    Raises:
        PasswordsExtensionMissing: if there's no extension to copy.
        ProfileAccessDenied: if its files are there but can't be read.
    """
    if not _has_manifest(source):
        raise PasswordsExtensionMissing(
            f"No iCloud Passwords extension to copy from: "
            f"{source / 'manifest.json'}. Install it in Chrome first, or "
            "capture without --passwords."
        )

    staged_manifest = into / "manifest.json"
    try:
        shutil.copytree(source, into)
        manifest = json.loads(staged_manifest.read_text())
    except OSError as exc:
        # macOS can allow listing a folder while denying the files in it, so a
        # manifest we could stat above is no promise the copy will work.
        # shutil.Error, which copytree raises for a per-file failure, is an
        # OSError too.
        raise _profile_access_denied(source, exc) from exc
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
    # Chrome takes the URL to open as its one positional argument.
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


class _CallRefused(_BrowserGone):
    """Chrome answered the call with an error.

    A browser that refuses one call is usually a browser on its way out, which
    is why this counts as gone, but a page that has nothing to evaluate in yet
    refuses the same way and is worth retrying.
    """


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
        # A Chrome that has gone takes both ends of the pipe with it, and the
        # write is where that shows first: asking a dead browser for cookies
        # raises ConnectionResetError here, not on the read below.
        try:
            self._writer.write(json.dumps(request).encode() + b"\0")
            await self._writer.drain()
        except OSError as exc:
            raise _BrowserGone("Chrome closed the DevTools pipe") from exc

        while True:
            try:
                raw = await self._reader.readuntil(b"\0")
            except (asyncio.IncompleteReadError, OSError) as exc:
                raise _BrowserGone("Chrome closed the DevTools pipe") from exc
            message = json.loads(raw[:-1])
            if message.get("id") != self._next_id:
                continue  # An event, or a reply we no longer wait for.
            if "error" in message:
                raise _CallRefused(message["error"].get("message", method))
            return message["result"]

    async def pages(self) -> list[str]:
        """The URL each open page is showing, one call for count and contents."""
        targets = await self._call("Target.getTargets")
        return [t.get("url", "") for t in targets["targetInfos"] if t["type"] == "page"]

    async def load_extension(self, path: Path) -> str:
        """Installs an unpacked extension and returns the ID Chrome gave it."""
        result = await self._call("Extensions.loadUnpacked", {"path": str(path)})
        return str(result["id"])

    async def reload(self) -> None:
        """Loads the open page again, so a just-loaded extension runs on it.

        Content scripts are injected as a page loads, so an extension that
        arrives after the window is up only reaches the next load.
        """
        targets = await self._call("Target.getTargets")
        pages = [t for t in targets["targetInfos"] if t["type"] == "page"]
        if not pages:
            raise _BrowserGone("Chrome has no window to reload")
        attached = await self._call(
            "Target.attachToTarget", {"targetId": pages[0]["targetId"], "flatten": True}
        )
        await self._call("Page.reload", session=attached["sessionId"])

    async def cookies(self) -> list[dict[str, Any]]:
        result = await self._call("Storage.getCookies")
        return list(result["cookies"])

    async def user_agent(self) -> str:
        """The user agent string this browser puts on its requests."""
        version = await self._call("Browser.getVersion")
        return str(version["userAgent"])

    async def page_identity(self) -> dict[str, Any]:
        """Asks the open page for the metadata behind the browser's hints.

        Returns:
            What :data:`IDENTITY_SCRIPT` read, or an empty dict if the page
            never got as far as answering. A sign-in is worth more than the
            hints, so a page that can't answer costs the capture nothing.
        """
        session: str | None = None
        try:
            async with asyncio.timeout(IDENTITY_GRACE):
                while True:
                    if session is None:
                        session = await self._page_session()
                    if session is not None:
                        read = await self._read_identity(session)
                        # A window still waiting for its first page holds the
                        # empty document it opened with, which is not a secure
                        # context and so knows nothing about the browser. The
                        # target already reports the URL it is on its way to,
                        # so the document is what has to be asked.
                        if read.get("href", "about:blank") != "about:blank":
                            return read
                    await asyncio.sleep(POLL_INTERVAL)
        except TimeoutError:
            return {}

    async def _read_identity(self, session: str) -> dict[str, Any]:
        """Runs the identity script in a page, or nothing if it can't run yet."""
        try:
            return await self._evaluate(session, IDENTITY_SCRIPT)
        except _CallRefused:
            # The page has no execution context to evaluate in yet, or it
            # navigated away from the one it had.
            return {}

    async def _page_session(self) -> str | None:
        """A DevTools session on the page the capture opened, if it is there."""
        targets = await self._call("Target.getTargets")
        pages = [
            target for target in targets["targetInfos"] if target["type"] == "page"
        ]
        if not pages:
            return None
        attached = await self._call(
            "Target.attachToTarget", {"targetId": pages[0]["targetId"], "flatten": True}
        )
        return str(attached["sessionId"])

    async def _evaluate(self, session: str, expression: str) -> dict[str, Any]:
        """Runs one expression in a page and brings its value back."""
        result = await self._call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            session=session,
        )
        return dict(result["result"]["value"])

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


async def _capture_async(
    *,
    identity: bool,
    url: str,
    domains: Iterable[str] | None = None,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None = None,
    until_values: Iterable[str] | None = None,
    until_url: str | None = None,
    settle: float = 0.0,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
    on_progress: Callable[[list[str]], None] | None = None,
) -> CapturedSession:
    """The one capture every public way in passes through.

    ``identity`` asks the browser what it is, which means running one
    expression in the page someone is about to sign in on, so a capture
    that doesn't need it doesn't pay for it.
    """
    wanted = conditions.build(
        until=until, until_values=until_values, until_url=until_url
    )

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

    keep = frozenset(domains or ())
    profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))
    staging = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX)) if passwords else None
    # Always opened on the sign-in page itself, extension or not: Chrome leaves
    # the keyboard in the address bar on a window that opens empty, and
    # navigating afterwards doesn't move it onto the page, so what the person
    # types never reaches the form.
    browser = _Chrome(chrome, profile, url, proxy)
    # Seeded with every condition, so a timeout before the first poll still
    # says what the capture was waiting for.
    progress = Progress(pending=wanted.describe())

    user_agent = ""
    page: dict[str, Any] = {}

    try:
        await browser.start()
        if extension_source is not None and staging is not None:
            await browser.load_extension(
                stage_passwords_extension(extension_source, staging / "extension")
            )
            # The page was already up when the extension arrived, so it has to
            # load again for the extension's content scripts to run on it.
            await browser.reload()
        try:
            async with asyncio.timeout(timeout):
                if identity:
                    # Read before the first poll, so that however the browser
                    # ends afterwards, the session still knows what it was. A
                    # browser already gone is diagnosed by the poll below,
                    # which knows whether the sign-in got anywhere.
                    try:
                        user_agent = await browser.user_agent()
                        page = await browser.page_identity()
                    except _BrowserGone:
                        pass
                    progress.seen_a_window = bool(page)
                cookies = await _wait_for_cookies(
                    browser, keep, wanted, settle, on_progress, progress
                )
                return _session(cookies, user_agent, page, progress)
        except TimeoutError as exc:
            if progress.settling:
                # The conditions did hold; only the settle wait ran out.
                return _session(progress.cookies, user_agent, page, progress)
            waited_for = (
                ", ".join(progress.pending) if wanted else "the browser to close"
            )
            raise CaptureTimeout(
                f"Timed out after {timeout:g}s waiting for {waited_for}"
                + _elsewhere(progress)
            ) from exc
    finally:
        try:
            await browser.stop()
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)


def _session(
    cookies: list[Cookie],
    user_agent: str,
    page: dict[str, Any],
    progress: Progress,
) -> CapturedSession:
    """Puts the cookies and what the browser said it is into one answer."""
    metadata = page.get("metadata")
    languages = page.get("languages")
    return CapturedSession(
        cookies=cookies,
        user_agent=user_agent,
        client_hints=client_hints(metadata),
        high_entropy_hints=high_entropy_hints(metadata),
        accept_language=accept_language(languages) if languages else None,
        final_url=progress.final_url,
    )


def _page_url(open_pages: list[str]) -> str | None:
    """Where a sign-in has got to, out of the pages that are open.

    Only pages someone could have signed in on count, since Chrome's own tabs
    and blank windows come and go.
    """
    for url in open_pages:
        if url.startswith(PAGE_SCHEMES):
            return url
    return None


def _elsewhere(progress: Progress) -> str:
    """Points at cookies that did arrive, but on a domain that wasn't asked for.

    Domains don't match by subdomain, so asking for ``example.com`` when the
    cookie lands on ``www.example.com`` otherwise just waits out the clock.
    """
    sightings = [
        f"{name} on {', '.join(sorted(domains))}"
        for name, domains in sorted(progress.elsewhere.items())
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
    domains: frozenset[str],
    wanted: Conditions,
    settle: float,
    on_progress: Callable[[list[str]], None] | None,
    progress: Progress,
) -> list[Cookie]:
    """Polls the browser until the conditions hold or it goes away.

    Closing the last window makes Chrome tear down the session, and its cookies
    stop being readable, so each pass takes a snapshot and only then checks
    whether a window is still there. That leaves the last snapshot as the
    answer, taken as late as it can be, and it lives on ``progress`` so that a
    browser which vanishes mid-poll doesn't take it down.
    """
    loop = asyncio.get_running_loop()
    met_at: float | None = None

    if wanted and on_progress is not None:
        on_progress(list(progress.pending))

    while True:
        try:
            snapshot = [to_cookie(raw) for raw in await browser.cookies()]
            open_pages = await browser.pages()
        except _BrowserGone as exc:
            if progress.seen_a_window:
                return _finish_on_close(wanted, progress)
            raise CaptureIncomplete(f"Chrome quit before signing in: {exc}") from exc

        # A browser on its way out can report an emptied store rather than
        # failing outright, and that is exactly the poll a capture ends on, so
        # it must not replace what the sign-in actually set.
        if open_pages or snapshot or not progress.cookies:
            _record(snapshot, domains, wanted, progress)
        if open_pages:
            progress.seen_a_window = True
            progress.final_url = _page_url(open_pages) or progress.final_url
        _report(wanted, open_pages, on_progress, progress)

        if wanted and met_at is None and progress.satisfied:
            met_at = loop.time()
            progress.settling = True
        if met_at is not None and loop.time() - met_at >= settle:
            return progress.cookies

        if not open_pages and progress.seen_a_window:
            return _finish_on_close(wanted, progress)

        await asyncio.sleep(POLL_INTERVAL)


def _record(
    snapshot: list[Cookie],
    domains: frozenset[str],
    wanted: Conditions,
    progress: Progress,
) -> None:
    """Keeps the cookies for the asked-for domains, and notes where the rest went.

    A wanted name seen on a domain nobody asked for is remembered, so a
    fruitless wait can say so instead of just running out of time.
    """
    patterns = wanted.name_patterns()
    kept: list[Cookie] = []
    for cookie in snapshot:
        if not domains or any(domain_matches(cookie.domain, d) for d in domains):
            kept.append(cookie)
        elif any(fnmatchcase(cookie.name, pattern) for pattern in patterns):
            progress.elsewhere.setdefault(cookie.name, set()).add(cookie.domain)
    progress.cookies = kept


def _report(
    wanted: Conditions,
    open_pages: list[str],
    on_progress: Callable[[list[str]], None] | None,
    progress: Progress,
) -> None:
    """Re-reads the conditions, and says so when what's outstanding changes."""
    pending = wanted.pending(progress.cookies, open_pages)
    changed = pending != progress.pending
    progress.pending = pending
    if changed and on_progress is not None:
        on_progress(pending)


def _finish_on_close(wanted: Conditions, progress: Progress) -> list[Cookie]:
    """Decides what the browser ending means: done, or ended too early.

    Closing the last window, quitting Chrome and Chrome exiting on its own all
    arrive here, and all answer with the last snapshot taken before the end.
    """
    if not wanted or progress.settling or progress.satisfied:
        return progress.cookies
    raise CaptureIncomplete(
        "The browser closed before the capture was done, still waiting for: "
        + ", ".join(progress.pending)
        + _elsewhere(progress)
    )


async def capture_async(
    *,
    url: str,
    domains: Iterable[str] | None = None,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None = None,
    until_values: Iterable[str] | None = None,
    until_url: str | None = None,
    settle: float = 0.0,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
    on_progress: Callable[[list[str]], None] | None = None,
) -> list[Cookie]:
    """Opens a throwaway Chrome window and returns the cookies a sign-in sets.

    The browser starts on a fresh profile with no history or logins, loads
    ``url`` and waits for the person to sign in by hand. cookietuner never
    types, fills or reads credentials.

    The capture finishes on the first poll where every condition given holds at
    once. Without any condition, it finishes when the browser does.

    Args:
        url: Page to open, usually a sign-in form.
        domains: Only return cookies set for exactly these domains, matched the
                 same way as ``cookies`` (a leading dot is ignored, subdomains
                 don't match). Every domain is returned when this is empty.
        until: Cookie names to wait for, as names or globs. A name is also
               matched by a complete chunk set (``name.0``, ``name.1``, …).
               Alternatively a predicate, called on each poll with the cookies
               that would be returned.
        until_values: Cookie value conditions, each ``name=glob`` or
                      ``name!=glob``. The cookie has to exist either way, which
                      is what tells a signed-in session from an anonymous one
                      that reuses the name.
        until_url: Glob an open page's URL must match, or, prefixed with ``!``,
                   must not: ``"!*/login*"`` waits until the sign-in page is
                   left.
        settle: Seconds to keep polling after the conditions first hold,
                returning the last snapshot. Late cookies, trailing chunks and
                post-login redirects land in that window.
        timeout: Seconds to wait before giving up.
        passwords: Load Apple's iCloud Passwords extension, so signing in can
                   use the Passwords app instead of typing. The profile is new
                   every time, so expect the extension's pairing step on every
                   capture.
        proxy: Proxy for the browser's traffic, e.g. ``socks5://host:1080``.
        on_progress: Called with the conditions still outstanding, as a list of
                     short descriptions, whenever that list changes. Values and
                     live URLs are never part of it.

    Returns:
        The cookies in effect when the wait finished, including HttpOnly and
        session cookies that never reach disk, exactly as the browser had them.
        A chunked cookie comes back in chunks; :func:`join_chunks` reassembles
        one.

    Raises:
        ValueError: if a condition is malformed. Checked before Chrome starts.
        ChromeNotFound: if Google Chrome isn't installed.
        CaptureTimeout: if ``timeout`` passes before the conditions hold.
        CaptureIncomplete: if the browser ends before they do.
        ProfileAccessDenied: if ``passwords`` is set and Chrome's profile
                             folder can't be read.
        PasswordsExtensionMissing: if ``passwords`` is set and the extension
                                   isn't installed to copy from.
    """
    session = await _capture_async(
        identity=False,
        url=url,
        domains=domains,
        until=until,
        until_values=until_values,
        until_url=until_url,
        settle=settle,
        timeout=timeout,
        passwords=passwords,
        proxy=proxy,
        on_progress=on_progress,
    )
    return session.cookies


def capture(
    *,
    url: str,
    domains: Iterable[str] | None = None,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None = None,
    until_values: Iterable[str] | None = None,
    until_url: str | None = None,
    settle: float = 0.0,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
    on_progress: Callable[[list[str]], None] | None = None,
) -> list[Cookie]:
    """Blocking version of :func:`capture_async`, for scripts."""
    return asyncio.run(
        capture_async(
            url=url,
            domains=domains,
            until=until,
            until_values=until_values,
            until_url=until_url,
            settle=settle,
            timeout=timeout,
            passwords=passwords,
            proxy=proxy,
            on_progress=on_progress,
        )
    )


async def capture_session_async(
    *,
    url: str,
    domains: Iterable[str] | None = None,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None = None,
    until_values: Iterable[str] | None = None,
    until_url: str | None = None,
    settle: float = 0.0,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
    on_progress: Callable[[list[str]], None] | None = None,
) -> CapturedSession:
    """The same capture as :func:`capture_async`, and the browser with it.

    Same arguments, same conditions, same errors. A session sent from a
    browser that didn't sign in is what a site sees as a stolen one, so
    this returns the identity to send the cookies back with.

    The identity is read once the window is up and before the first poll,
    so it comes back however the capture ends. Reading it runs one
    expression in the page: an insecure page has no client hints to give,
    and leaves those out rather than ending the capture.

    Returns:
        The cookies :func:`capture_async` would return, the user agent,
        client hints and language of the browser that set them, and the
        page the sign-in ended on.
    """
    return await _capture_async(
        identity=True,
        url=url,
        domains=domains,
        until=until,
        until_values=until_values,
        until_url=until_url,
        settle=settle,
        timeout=timeout,
        passwords=passwords,
        proxy=proxy,
        on_progress=on_progress,
    )


def capture_session(
    *,
    url: str,
    domains: Iterable[str] | None = None,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None = None,
    until_values: Iterable[str] | None = None,
    until_url: str | None = None,
    settle: float = 0.0,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
    on_progress: Callable[[list[str]], None] | None = None,
) -> CapturedSession:
    """Blocking version of :func:`capture_session_async`, for scripts."""
    return asyncio.run(
        capture_session_async(
            url=url,
            domains=domains,
            until=until,
            until_values=until_values,
            until_url=until_url,
            settle=settle,
            timeout=timeout,
            passwords=passwords,
            proxy=proxy,
            on_progress=on_progress,
        )
    )
