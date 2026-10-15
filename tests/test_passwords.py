# ABOUTME: Tests for loading Apple's iCloud Passwords extension into a capture
# ABOUTME: Checks the extension keeps the store ID its native helper will talk to

import base64
import hashlib
import json
from pathlib import Path

import pytest

from cookietuner.capture import (
    PASSWORDS_EXTENSION_ID,
    PASSWORDS_EXTENSION_KEY,
    chrome_app_path,
    passwords_extension_source,
    stage_passwords_extension,
)
from cookietuner.errors import PasswordsExtensionMissing


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
    chrome_app_path() is None or passwords_extension_source() is None,
    reason="Chrome with the iCloud Passwords extension is not installed",
)


@requires_extension
def test_the_installed_extension_is_found_with_a_manifest() -> None:
    source = passwords_extension_source()
    assert source is not None
    assert (source / "manifest.json").exists()


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
