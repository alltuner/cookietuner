# ABOUTME: Errors shared by the cookie backends
# ABOUTME: Distinguishes a store we may not read from one that isn't there


class CookieStoreUnreadable(Exception):
    """A browser's cookie store exists but this process may not read it."""


class CaptureError(Exception):
    """A sign-in capture could not produce the cookies that were asked for."""


class ChromeNotFound(CaptureError):
    """Google Chrome isn't installed where we look for it."""


class CaptureTimeout(CaptureError):
    """The wait ran out before the cookies appeared."""


class BrowserClosedEarly(CaptureError):
    """Chrome quit, or its window closed, before the cookies appeared."""
