# ABOUTME: Pydantic models for cookie data structures
# ABOUTME: Defines Cookie, a captured session and browser profile configuration

from datetime import datetime, timezone

from pydantic import BaseModel, Field, computed_field


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


class CapturedSession(BaseModel):
    """The cookies a sign-in set, and the browser that signed in.

    A session sent from a browser that didn't sign in is what a site sees as a
    stolen one, so the identity it was captured with travels with the cookies.
    """

    cookies: list[Cookie]
    user_agent: str
    # Empty when the page the capture opened had no user-agent metadata to
    # give, which an insecure origin never does, and is sent no hints either.
    client_hints: dict[str, str] = Field(default_factory=dict)
    high_entropy_hints: dict[str, str] = Field(default_factory=dict)
    accept_language: str | None = None
    final_url: str | None = None

    def headers(self) -> dict[str, str]:
        """The request headers this browser sends without being asked.

        The high-entropy hints are left out, because a site only receives
        those when it asks for them with ``Accept-CH``.
        """
        headers = {"User-Agent": self.user_agent}
        if self.accept_language:
            headers["Accept-Language"] = self.accept_language
        headers.update(self.client_hints)
        return headers


class BrowserProfile(BaseModel):
    """Represents a browser profile location."""

    browser: str
    profile_name: str
    path: str
