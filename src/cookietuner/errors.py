# ABOUTME: Errors shared by the cookie backends and the sign-in capture
# ABOUTME: Each capture error carries the exit code the CLI reports it with


class CookieStoreUnreadable(Exception):
    """A browser's cookie store exists but this process may not read it."""


class CaptureError(Exception):
    """A sign-in capture could not produce the cookies that were asked for.

    ``exit_code`` is what the CLI exits with, so a script can tell these apart
    without parsing a message. 2 is left alone, because that is what the
    command line itself exits with when an option is wrong.
    """

    exit_code = 1


class CaptureTimeout(CaptureError):
    """The wait ran out before the conditions held."""

    exit_code = 3


class CaptureIncomplete(CaptureError):
    """The browser ended before the conditions held."""

    exit_code = 4


class ChromeNotFound(CaptureError):
    """Google Chrome isn't installed where we look for it."""

    exit_code = 5


class ProfileAccessDenied(CaptureError):
    """Chrome's profile folder is there, but this process may not read it."""

    exit_code = 6


class PasswordsExtensionMissing(CaptureError):
    """Apple's iCloud Passwords extension isn't installed to copy from."""

    exit_code = 7
