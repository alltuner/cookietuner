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
