# ABOUTME: Cookie extraction tool for macOS browsers
# ABOUTME: Public entry points: the CLI, the capture functions and their models

from .capture import capture, capture_async, capture_session, capture_session_async
from .cli import main
from .conditions import join_chunks
from .errors import (
    CaptureError,
    CaptureIncomplete,
    CaptureTimeout,
    ChromeNotFound,
    CookieStoreUnreadable,
    PasswordsExtensionMissing,
    ProfileAccessDenied,
)
from .models import CapturedSession, Cookie

__all__ = [
    "CaptureError",
    "CaptureIncomplete",
    "CaptureTimeout",
    "CapturedSession",
    "ChromeNotFound",
    "Cookie",
    "CookieStoreUnreadable",
    "PasswordsExtensionMissing",
    "ProfileAccessDenied",
    "capture",
    "capture_async",
    "capture_session",
    "capture_session_async",
    "join_chunks",
    "main",
]
