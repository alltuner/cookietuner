# ABOUTME: Chrome cookie extraction for macOS
# ABOUTME: Reads and decrypts cookies from Chrome's SQLite database

import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .domain import domain_matches
from .errors import CookieStoreUnreadable
from .models import BrowserProfile, Cookie

# Chrome uses microseconds since Jan 1, 1601 (Windows epoch)
CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)

SAME_SITE_MAP: dict[int, str | None] = {
    -1: None,
    0: "none",
    1: "lax",
    2: "strict",
}

CHROME_BASE_PATH = Path.home() / "Library/Application Support/Google/Chrome"


def _unreadable(path: Path, exc: OSError) -> CookieStoreUnreadable:
    """Builds the error for a path macOS lets us stat but not read."""
    return CookieStoreUnreadable(
        f"Chrome's profile data is unreadable: {path}: {exc.strerror}. "
        "On macOS 27 this folder is restricted to Chrome itself, and Full Disk "
        "Access does not lift it; on earlier versions, grant Full Disk Access "
        "to your terminal."
    )


def list_profiles() -> list[BrowserProfile]:
    """Lists all available Chrome profiles.

    Raises:
        CookieStoreUnreadable: if the profile folder can be stat'd but not listed.
    """
    profiles = []

    if not CHROME_BASE_PATH.exists():
        return profiles

    try:
        items = sorted(CHROME_BASE_PATH.iterdir())
    except OSError as exc:
        raise _unreadable(CHROME_BASE_PATH, exc) from exc

    for item in items:
        if item.is_dir():
            cookies_file = item / "Cookies"
            if cookies_file.exists():
                # "Default" is the main profile, others are "Profile 1", "Profile 2", etc.
                profile_name = item.name
                if profile_name == "Default":
                    profile_name = "Default"
                profiles.append(
                    BrowserProfile(
                        browser="chrome",
                        profile_name=profile_name,
                        path=str(item),
                    )
                )

    return profiles


def _get_cookie_path(profile: str = "Default") -> Path:
    """Returns the path to Chrome's cookie database for a given profile."""
    return CHROME_BASE_PATH / profile / "Cookies"


def _get_encryption_key() -> bytes:
    """Retrieves Chrome's encryption key from macOS Keychain."""
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-s",
            "Chrome Safe Storage",
            "-w",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    password = result.stdout.strip()

    # Derive the key using PBKDF2
    # Chrome uses "saltysalt" as salt and 1003 iterations on macOS
    key = pbkdf2_hmac(
        "sha1",
        password.encode("utf-8"),
        b"saltysalt",
        1003,
        dklen=16,
    )
    return key


def _decrypt_value(encrypted_value: bytes, key: bytes, strip_hash: bool) -> str:
    """Decrypts a Chrome cookie value."""
    if not encrypted_value:
        return ""

    # Chrome prepends 'v10' to encrypted values on macOS
    if encrypted_value[:3] == b"v10":
        encrypted_value = encrypted_value[3:]

        # Chrome uses AES-128-CBC with a 16-byte IV of spaces
        iv = b" " * 16
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        decrypted = decrypted[:-padding_len]

        # Chrome 130+ (DB version >= 24) prepends SHA256 hash of domain (32 bytes)
        if strip_hash:
            decrypted = decrypted[32:]

        return decrypted.decode("utf-8")

    # Unencrypted value (older Chrome versions)
    return encrypted_value.decode("utf-8")


def _get_db_version(cursor: sqlite3.Cursor) -> int:
    """Gets the cookie database version from the meta table."""
    cursor.execute("SELECT value FROM meta WHERE key='version'")
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def _chrome_time_to_datetime(chrome_time: int) -> datetime | None:
    """Converts Chrome's timestamp (microseconds since 1601) to datetime."""
    if chrome_time == 0:
        return None
    try:
        seconds = chrome_time / 1_000_000
        return CHROME_EPOCH + timedelta(seconds=seconds)
    except (ValueError, OverflowError):
        return None


def get_cookies(
    domain: str | None = None,
    profile: str = "Default",
) -> list[Cookie]:
    """
    Reads cookies from Chrome's cookie database.

    Args:
        domain: If specified, only return cookies set for exactly this
                domain (a leading dot is ignored, subdomains don't match).
        profile: Chrome profile to read from (default: "Default").

    Returns:
        List of Cookie objects.

    Raises:
        CookieStoreUnreadable: if the cookie file can be stat'd but not read.
    """
    cookie_path = _get_cookie_path(profile)

    if not cookie_path.exists():
        return []

    # Copy the database to avoid locking issues while Chrome is running
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Copy before reading the Keychain, so an unreadable store fails without
        # first prompting for Keychain access.
        try:
            shutil.copy2(cookie_path, tmp_path)
        except OSError as exc:
            raise _unreadable(cookie_path, exc) from exc

        key = _get_encryption_key()

        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()

        # Check if we need to strip the hash prefix (Chrome 130+)
        db_version = _get_db_version(cursor)
        strip_hash = db_version >= 24

        query = """
            SELECT host_key, name, encrypted_value, path,
                   expires_utc, is_secure, is_httponly, samesite
            FROM cookies
        """
        params: tuple[str, ...] = ()

        if domain:
            # Cheap SQL prefilter; domain_matches below makes it exact.
            query += " WHERE host_key LIKE ?"
            params = (f"%{domain.lstrip('.')}",)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        cookies = []
        for (
            host_key,
            name,
            encrypted_value,
            path,
            expires_utc,
            is_secure,
            is_httponly,
            samesite,
        ) in rows:
            if domain and not domain_matches(host_key, domain):
                continue
            try:
                value = _decrypt_value(encrypted_value, key, strip_hash)
                cookies.append(
                    Cookie(
                        domain=host_key,
                        name=name,
                        value=value,
                        path=path,
                        expires=_chrome_time_to_datetime(expires_utc),
                        is_secure=bool(is_secure),
                        is_httponly=bool(is_httponly),
                        same_site=SAME_SITE_MAP.get(samesite, "unspecified"),
                    )
                )
            except Exception:
                # Skip cookies that fail to decrypt
                pass

        return cookies

    finally:
        tmp_path.unlink(missing_ok=True)
