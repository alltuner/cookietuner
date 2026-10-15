# ABOUTME: Tests for loading Apple's iCloud Passwords extension into a capture
# ABOUTME: Checks the extension keeps the store ID its native helper will talk to

import base64
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

from cookietuner.capture import (
    PASSWORDS_EXTENSION_ID,
    PASSWORDS_EXTENSION_KEY,
    capture,
    chrome_app_path,
    passwords_extension_source,
    stage_passwords_extension,
)
from cookietuner.errors import PasswordsExtensionMissing, ProfileAccessDenied

from .conftest import KEYBOARD_TIMEOUT

# Fetched this way because the package re-exports the capture function over its
# own module's name, so both `from cookietuner import capture` and monkeypatch's
# dotted lookup find the function instead of the module these globals live in.
capture_module = importlib.import_module("cookietuner.capture")

# chmod means nothing to root, so the denial tests can't say anything there.
_needs_an_unprivileged_user = pytest.mark.skipif(
    os.geteuid() == 0, reason="running as root, which no permission can stop"
)


def installed_extension() -> Path | None:
    """The installed extension, or None if it isn't there or can't be read.

    Used to decide whether to skip, so a profile this process may not read
    doesn't take test collection down with it.
    """
    try:
        return passwords_extension_source()
    except ProfileAccessDenied:
        return None


def test_the_embedded_key_derives_the_store_extension_id() -> None:
    """Chrome's ID is SHA256 of the public key, so the key can't drift from it."""
    digest = hashlib.sha256(base64.b64decode(PASSWORDS_EXTENSION_KEY)).hexdigest()[:32]
    derived = "".join(chr(ord("a") + int(c, 16)) for c in digest)
    assert derived == PASSWORDS_EXTENSION_ID


def test_staging_puts_the_key_back_into_the_manifest(tmp_path: Path) -> None:
    """A loaded copy only keeps the store ID if its manifest carries the key."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "iCloud Passwords", "version": "1"})
    )
    (source / "background.js").write_text("// content\n")

    staged = stage_passwords_extension(source, tmp_path / "staged")

    manifest = json.loads((staged / "manifest.json").read_text())
    assert manifest["key"] == PASSWORDS_EXTENSION_KEY
    assert manifest["name"] == "iCloud Passwords"
    # The rest of the extension has to come along with it.
    assert (staged / "background.js").read_text() == "// content\n"


def test_staging_reports_a_missing_extension(tmp_path: Path) -> None:
    with pytest.raises(PasswordsExtensionMissing):
        stage_passwords_extension(tmp_path / "absent", tmp_path / "staged")


requires_extension = pytest.mark.skipif(
    chrome_app_path() is None or installed_extension() is None,
    reason="Chrome with the iCloud Passwords extension is not installed",
)


@requires_extension
def test_the_installed_extension_is_found_with_a_manifest() -> None:
    source = passwords_extension_source()
    assert source is not None
    assert (source / "manifest.json").exists()


def test_an_absent_profile_means_the_extension_is_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capture_module, "CHROME_BASE_PATH", tmp_path / "nothing-here")

    assert passwords_extension_source() is None


@_needs_an_unprivileged_user
def test_an_unreadable_profile_is_not_a_missing_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The error that sent people looking for an extension they already had.

    macOS can refuse the profile folder outright, which used to come back as
    "the extension isn't installed", pointing at the wrong fix entirely.
    """
    profile = tmp_path / "Default"
    profile.mkdir()
    monkeypatch.setattr(capture_module, "CHROME_BASE_PATH", tmp_path)
    profile.chmod(0o000)

    try:
        with pytest.raises(ProfileAccessDenied) as caught:
            passwords_extension_source()
    finally:
        profile.chmod(0o700)

    assert "Full Disk Access" in str(caught.value)


@_needs_an_unprivileged_user
def test_an_unreadable_extension_folder_is_a_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extensions = tmp_path / "Default" / "Extensions" / PASSWORDS_EXTENSION_ID
    extensions.mkdir(parents=True)
    monkeypatch.setattr(capture_module, "CHROME_BASE_PATH", tmp_path)
    extensions.chmod(0o000)

    try:
        with pytest.raises(ProfileAccessDenied):
            passwords_extension_source()
    finally:
        extensions.chmod(0o700)


@_needs_an_unprivileged_user
def test_a_manifest_that_cannot_be_read_is_a_denial(tmp_path: Path) -> None:
    """Listing a folder and reading what's in it are separate permissions.

    Chrome's own profile can be listable while its files are denied, and
    Path.is_file answers False either way, so staging is where it surfaces.
    """
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text(json.dumps({"manifest_version": 3}))
    (source / "manifest.json").chmod(0o000)

    try:
        with pytest.raises(ProfileAccessDenied):
            stage_passwords_extension(source, tmp_path / "staged")
    finally:
        (source / "manifest.json").chmod(0o600)


@pytest.mark.browser
@requires_extension
def test_chrome_loads_the_extension_under_its_store_id(tmp_path: Path) -> None:
    """The native helper only talks to the store ID, so this is the whole point.

    Driving real Chrome here, because a wrong ID is exactly the failure that
    would otherwise only show up as silently broken autofill.
    """
    import asyncio

    from cookietuner.capture import _Chrome

    source = passwords_extension_source()
    assert source is not None
    staged = stage_passwords_extension(source, tmp_path / "staged")
    chrome = chrome_app_path()
    assert chrome is not None

    async def load() -> str:
        profile = tmp_path / "profile"
        profile.mkdir()
        browser = _Chrome(chrome, profile, "about:blank", None)
        try:
            await browser.start()
            return await browser.load_extension(staged)
        finally:
            await browser.stop()

    assert asyncio.run(load()) == PASSWORDS_EXTENSION_ID


@pytest.mark.browser
@requires_extension
def test_the_extension_window_gives_the_sign_in_page_the_keyboard(
    keyboard_url: str,
) -> None:
    """Nobody can sign in from the Passwords app into a window that won't type.

    The extension arrives after the window is up, which is why the page is
    reloaded rather than opened blank and navigated: an empty window leaves
    the keyboard in the address bar, and navigating doesn't move it.
    """
    cookies = capture(
        url=keyboard_url,
        until=["keyboard"],
        until_values=["keyboard=page"],
        timeout=KEYBOARD_TIMEOUT,
        passwords=True,
    )
    assert [c.value for c in cookies if c.name == "keyboard"] == ["page"]
