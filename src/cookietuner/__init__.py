# ABOUTME: Cookie extraction tool for macOS browsers
# ABOUTME: Public entry points: the CLI, the capture functions and the Cookie model

from .capture import capture, capture_async
from .cli import main
from .errors import (
    BrowserClosedEarly,
    CaptureError,
    CaptureTimeout,
    ChromeNotFound,
    CookieStoreUnreadable,
    PasswordsExtensionMissing,
)
from .models import Cookie

__all__ = [
    "BrowserClosedEarly",
    "CaptureError",
    "CaptureTimeout",
    "ChromeNotFound",
    "Cookie",
    "CookieStoreUnreadable",
    "PasswordsExtensionMissing",
    "capture",
    "capture_async",
    "main",
]
