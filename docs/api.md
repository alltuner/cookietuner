# API Reference

cookietuner can also be used as a Python library.

## Models

### Cookie

```python
from cookietuner.models import Cookie

cookie = Cookie(
    domain=".example.com",
    name="session",
    value="abc123",
    path="/",
    expires=datetime(2025, 12, 31),
    is_secure=True,
    is_httponly=True,
    same_site="lax",
)

# Computed property
cookie.is_expired  # False
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `domain` | `str` | Cookie domain |
| `name` | `str` | Cookie name |
| `value` | `str` | Cookie value |
| `path` | `str` | Cookie path |
| `expires` | `datetime \| None` | Expiration time (None for session cookies) |
| `is_secure` | `bool` | Secure flag |
| `is_httponly` | `bool` | HttpOnly flag |
| `same_site` | `str \| None` | SameSite policy (none, lax, strict) |
| `is_expired` | `bool` | Computed: whether the cookie has expired |

## Chrome

### get_cookies

```python
from cookietuner.chrome import get_cookies

# Get all cookies
cookies = get_cookies()

# Filter by domain
cookies = get_cookies(domain="github.com")

# Specific profile
cookies = get_cookies(profile="Profile 1")
```

### list_profiles

```python
from cookietuner.chrome import list_profiles

profiles = list_profiles()
for p in profiles:
    print(f"{p.profile_name}: {p.path}")
```

## Capture

`capture` opens Google Chrome on a throwaway profile, waits while a person signs
in, and returns the cookies that session set. It reaches session and HttpOnly
cookies that never reach disk. The temporary profile is deleted when the capture
ends, including on timeout, cancellation or error.

### capture

```python
from cookietuner import Cookie, capture

cookies: list[Cookie] = capture(
    url="https://example.com/login",
    domain="example.com",
    until={"session_id", "csrf_token"},
    timeout=300,
    proxy=None,
)
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `url` | `str` | Page to open, usually a sign-in form |
| `domain` | `str \| None` | Keep only cookies for exactly this domain (leading dot ignored, subdomains don't match) |
| `until` | `set[str] \| None` | Cookie names to wait for. Without them, the capture ends when the last window closes |
| `timeout` | `float` | Seconds before giving up (default `300`) |
| `proxy` | `str \| None` | Proxy for the browser, e.g. `socks5://127.0.0.1:1080` |

### capture_async

The same thing for an async application. `capture` is a thin wrapper around it,
so both share one implementation:

```python
from cookietuner import capture_async

cookies = await capture_async(
    url="https://example.com/login",
    domain="example.com",
    until={"session_id"},
)
```

### Errors

All of these subclass `CaptureError`, and the temporary profile is cleaned up
before any of them is raised:

| Error | Raised when |
|-------|-------------|
| `ChromeNotFound` | Google Chrome isn't installed |
| `CaptureTimeout` | `timeout` passed before the cookies appeared |
| `BrowserClosedEarly` | Chrome quit, or the window closed, before the cookies appeared |

```python
from cookietuner import CaptureTimeout, capture

try:
    cookies = capture(url="https://example.com/login", until={"session_id"})
except CaptureTimeout as exc:
    print(f"gave up: {exc}")
```

## Safari

### get_cookies

```python
from cookietuner.safari import get_cookies

# Get all cookies
cookies = get_cookies()

# Filter by domain
cookies = get_cookies(domain="apple.com")
```

### list_profiles

```python
from cookietuner.safari import list_profiles

profiles = list_profiles()  # Safari only has one profile
```

## Example: Export cookies for requests

```python
from cookietuner.chrome import get_cookies
import requests

# Get cookies for a specific domain
cookies = get_cookies(domain="api.example.com")

# Create a requests session with the cookies
session = requests.Session()
for cookie in cookies:
    session.cookies.set(
        cookie.name,
        cookie.value,
        domain=cookie.domain,
        path=cookie.path,
    )

# Use the session
response = session.get("https://api.example.com/endpoint")
```
