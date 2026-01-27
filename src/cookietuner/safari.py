# ABOUTME: Safari cookie extraction for macOS
# ABOUTME: Parses the .binarycookies format used by Safari

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import BrowserProfile, Cookie

# Sandboxed Safari (modern macOS) stores cookies here
SAFARI_COOKIES_PATH_SANDBOXED = (
    Path.home()
    / "Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"
)
# Legacy location for older macOS versions
SAFARI_COOKIES_PATH_LEGACY = Path.home() / "Library/Cookies/Cookies.binarycookies"

# Safari uses Mac absolute time (seconds since Jan 1, 2001)
MAC_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# SameSite is encoded in bits 3-5 of the flags field
# https://gist.github.com/creachadair/ba843bd92c2cfc78dc5e1a53b44775a3
SAME_SITE_MAP: dict[int, str | None] = {
    0: None,  # unspecified
    4: "none",  # 0b100
    5: "lax",  # 0b101
    7: "strict",  # 0b111
}


def _get_cookies_path() -> Path | None:
    """Returns the path to Safari's cookies file, or None if not found."""
    for path in [SAFARI_COOKIES_PATH_SANDBOXED, SAFARI_COOKIES_PATH_LEGACY]:
        if path.exists():
            return path
    return None


def list_profiles() -> list[BrowserProfile]:
    """Safari only has one profile."""
    cookies_path = _get_cookies_path()
    if cookies_path is None:
        return []
    return [
        BrowserProfile(
            browser="safari",
            profile_name="Default",
            path=str(cookies_path),
        )
    ]


def _mac_time_to_datetime(mac_time: float) -> datetime | None:
    """Converts Mac absolute time to datetime."""
    if mac_time == 0:
        return None
    try:
        return MAC_EPOCH + timedelta(seconds=mac_time)
    except (ValueError, OverflowError):
        return None


def _read_cstring(data: bytes, offset: int) -> str:
    """Reads a null-terminated C string from data."""
    end = data.index(b"\x00", offset)
    return data[offset:end].decode("utf-8", errors="replace")


def _parse_cookie(data: bytes) -> Cookie | None:
    """Parses a single cookie from binary data."""
    try:
        # Cookie structure:
        # 4 bytes: cookie size
        # 4 bytes: unknown
        # 4 bytes: flags
        # 4 bytes: unknown
        # 4 bytes: domain offset
        # 4 bytes: name offset
        # 4 bytes: path offset
        # 4 bytes: value offset
        # 8 bytes: end of cookie
        # 8 bytes: expiration date (double)
        # 8 bytes: creation date (double)

        if len(data) < 48:
            return None

        flags = struct.unpack("<I", data[8:12])[0]
        domain_offset = struct.unpack("<I", data[16:20])[0]
        name_offset = struct.unpack("<I", data[20:24])[0]
        path_offset = struct.unpack("<I", data[24:28])[0]
        value_offset = struct.unpack("<I", data[28:32])[0]
        expiration = struct.unpack("<d", data[40:48])[0]

        domain = _read_cstring(data, domain_offset)
        name = _read_cstring(data, name_offset)
        path = _read_cstring(data, path_offset)
        value = _read_cstring(data, value_offset)

        is_secure = bool(flags & 0x1)
        is_httponly = bool(flags & 0x4)
        same_site_bits = (flags >> 3) & 0x7
        same_site = SAME_SITE_MAP.get(same_site_bits)

        return Cookie(
            domain=domain,
            name=name,
            value=value,
            path=path,
            expires=_mac_time_to_datetime(expiration),
            is_secure=is_secure,
            is_httponly=is_httponly,
            same_site=same_site,
        )
    except Exception:
        return None


def get_cookies(
    domain: str | None = None,
    profile: str = "Default",  # Safari only has one profile, ignored
) -> list[Cookie]:
    """
    Reads cookies from Safari's binarycookies file.

    Args:
        domain: If specified, only return cookies matching this domain.
        profile: Ignored for Safari (only one profile).

    Returns:
        List of Cookie objects.
    """
    cookies_path = _get_cookies_path()
    if cookies_path is None:
        return []

    with open(cookies_path, "rb") as f:
        data = f.read()

    cookies: list[Cookie] = []

    # File format:
    # 4 bytes: magic "cook"
    # 4 bytes: number of pages (big endian)
    # 4 bytes * num_pages: page sizes (big endian)
    # pages follow...

    if len(data) < 8 or data[:4] != b"cook":
        return cookies

    num_pages = struct.unpack(">I", data[4:8])[0]
    page_sizes = []

    offset = 8
    for _ in range(num_pages):
        page_sizes.append(struct.unpack(">I", data[offset : offset + 4])[0])
        offset += 4

    # Parse each page
    for page_size in page_sizes:
        page_data = data[offset : offset + page_size]
        offset += page_size

        if len(page_data) < 8:
            continue

        # Page header:
        # 4 bytes: page header (0x00000100)
        # 4 bytes: number of cookies in page
        # 4 bytes * num_cookies: cookie offsets

        num_cookies = struct.unpack("<I", page_data[4:8])[0]
        cookie_offsets = []

        page_offset = 8
        for _ in range(num_cookies):
            cookie_offsets.append(
                struct.unpack("<I", page_data[page_offset : page_offset + 4])[0]
            )
            page_offset += 4

        # Parse each cookie
        for i, cookie_offset in enumerate(cookie_offsets):
            # Determine cookie size
            if i + 1 < len(cookie_offsets):
                cookie_size = cookie_offsets[i + 1] - cookie_offset
            else:
                cookie_size = page_size - cookie_offset

            cookie_data = page_data[cookie_offset : cookie_offset + cookie_size]
            cookie = _parse_cookie(cookie_data)

            if cookie:
                if domain is None or domain.lower() in cookie.domain.lower():
                    cookies.append(cookie)

    return cookies
