# ABOUTME: Pydantic models for cookie data structures
# ABOUTME: Defines Cookie and browser profile configuration

from datetime import datetime, timezone

from pydantic import BaseModel, computed_field


class Cookie(BaseModel):
    """Represents a browser cookie with all attributes."""

    domain: str
    name: str
    value: str
    path: str
    expires: datetime | None = None
    is_secure: bool = False
    is_httponly: bool = False
    same_site: str | None = None

    @computed_field
    @property
    def is_expired(self) -> bool:
        """Returns True if the cookie has expired."""
        if self.expires is None:
            return False  # Session cookies don't expire
        now = datetime.now(timezone.utc)
        expires = (
            self.expires
            if self.expires.tzinfo
            else self.expires.replace(tzinfo=timezone.utc)
        )
        return expires < now

    def __str__(self) -> str:
        return f"{self.name}={self.value}"


class BrowserProfile(BaseModel):
    """Represents a browser profile location."""

    browser: str
    profile_name: str
    path: str
