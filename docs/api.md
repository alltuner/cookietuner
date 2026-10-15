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
    url: str,
    domains: Iterable[str] | None = None,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None = None,
    until_values: Iterable[str] | None = None,
    until_url: str | None = None,
    settle: float = 0.0,
    timeout: float = 300.0,
    passwords: bool = False,
    proxy: str | None = None,
    on_progress: Callable[[list[str]], None] | None = None,
)
```

All arguments are keyword-only.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `url` | `str` | required | Page to open, usually a sign-in form |
| `domains` | `Iterable[str] \| None` | `None` | Keep only cookies for exactly these domains (leading dot ignored, subdomains don't match). Every domain is kept when empty |
| `until` | `Iterable[str] \| Callable \| None` | `None` | Cookie names or globs to wait for, or a predicate |
| `until_values` | `Iterable[str] \| None` | `None` | Value conditions, each `name=glob` or `name!=glob` |
| `until_url` | `str \| None` | `None` | Glob an open page's URL must match, or must not when prefixed with `!` |
| `settle` | `float` | `0.0` | Seconds to keep polling after the conditions first hold |
| `timeout` | `float` | `300.0` | Seconds before giving up |
| `passwords` | `bool` | `False` | Load Apple's iCloud Passwords extension, copied from your own Chrome, to sign in from the Passwords app. Pairing is asked for on every capture, because the profile is new. This is the only option that needs access to your Chrome profile folder |
| `proxy` | `str \| None` | `None` | Proxy for the browser, e.g. `socks5://127.0.0.1:1080` |
| `on_progress` | `Callable[[list[str]], None] \| None` | `None` | Called with the conditions still outstanding whenever that list changes |

Returns the cookies in effect when the wait finished, exactly as the browser had
them: a chunked cookie comes back in chunks, and nothing is rewritten.

### When a capture is done

A capture finishes on the first poll where **every** condition given holds at
once. The browser is asked for its cookies and its open pages four times a
second.

- **Names** (`until`) match a cookie name, a glob (`*`, `?`, `[seq]`, matched
  case-sensitively), or a **complete chunk set**: `name.0`, `name.1`, … running
  from `.0` with no gap. Nothing in a cookie says how many chunks there will be,
  so a set looks complete as soon as it has `.0`, which is what `settle` is for.
  Chunks are only ever completed within one domain.
- **Values** (`until_values`) need the cookie to exist *and* its value to match,
  or, with `!=`, not to match. The cookie existing is part of the condition
  either way, so `uid!=anon_*` is not satisfied by `uid` being absent. The name
  side may be a glob too; the split is on the first `=`, so a pattern may
  contain more of them.
- **URL** (`until_url`) matches any open `http`/`https` page. Prefixed with
  `!`, it waits until none of them matches, which is how you wait to leave a
  sign-in page. Pages such as `about:blank` and Chrome's own tabs are ignored,
  so they can't stand in for having arrived or left.
- **A predicate** (`until` as a callable) is called on each poll with the
  cookies that would be returned, and covers anything the rest can't express.
- **`settle`** keeps polling for that many seconds after the conditions first
  hold, then returns the last snapshot. Late cookies, trailing chunks and
  post-login redirects land in that window. Once the conditions have held, the
  capture is done settling even if they stop holding, and if `timeout` runs out
  or the browser ends while it is settling it returns what it has rather than
  failing.

Given no conditions at all, the capture ends when the browser does, and `settle`
does nothing: there is nothing for it to settle after.

Malformed conditions raise `ValueError` before Chrome starts, so a typo costs
nothing.

### When the browser ends

Closing the last window, quitting Chrome (Cmd+Q) and Chrome exiting on its own
are all the same thing: the capture answers with the last snapshot it took
before the end. If conditions were given and that snapshot doesn't satisfy them,
it raises `CaptureIncomplete` rather than returning a partial session. The
temporary profile is removed in every case.

### capture_async

The same thing for an async application, with the same arguments. `capture` is a
thin wrapper around it, so both share one implementation:

```python
from cookietuner import capture_async

cookies = await capture_async(
    url="https://example.com/login",
    domains={"example.com", "auth.example.com"},
    until={"sb-*-auth-token"},
    until_url="*/dashboard*",
    settle=2,
)
```

### join_chunks

Reassembles a cookie an auth library split into `name.0`, `name.1`, … (Supabase's
SSR helpers do this above about 4 KB). `capture` never rewrites cookies, so this
is how you get the value back:

```python
from cookietuner import capture, join_chunks

cookies = capture(url="https://example.com/login", domains={"example.com"})
token = join_chunks(cookies, "sb-abcdef-auth-token")  # str | None
```

A cookie named exactly `name` wins over a chunk set. Returns `None` if neither a
whole cookie nor a complete set is there, and raises `ValueError` if the cookies
given hold more than one value for `name`, which a capture over several domains
can produce: filter to one domain first.

### main

The console-script entry point, `cookietuner` on the command line. Calling it
runs the CLI and exits the process, so a library should call `capture` instead.

```python
from cookietuner import main

main()
```

### Errors

`CaptureError` is the base class for every capture failure, and the temporary
profile is cleaned up before any of them is raised. Each carries the exit code
the CLI reports it with, as `exc.exit_code`, so a script can tell them apart
without reading messages. Messages name cookies and conditions, never values or
live URLs.

| Error | Exit code | Raised when |
|-------|-----------|-------------|
| `CaptureError` | 1 | Base class; also any capture failure with no more specific type |
| `CaptureTimeout` | 3 | `timeout` passed before the conditions held; names the unmet ones |
| `CaptureIncomplete` | 4 | The browser ended before the conditions held |
| `ChromeNotFound` | 5 | No usable Google Chrome |
| `ProfileAccessDenied` | 6 | Chrome's profile folder couldn't be read, with a hint about macOS privacy settings. Only `passwords=True` needs it |
| `PasswordsExtensionMissing` | 7 | The profile was readable but the iCloud Passwords extension isn't installed to copy from |

2 is left alone, because that is what the command line itself exits with when an
option is wrong.

`CookieStoreUnreadable` is separate, and does not subclass `CaptureError`: it is
raised by the store readers (`chrome.get_cookies`, `chrome.list_profiles`) when a
browser's cookie database exists but this process may not read it.

| Error | Raised when |
|-------|-------------|
| `CookieStoreUnreadable` | A browser's cookie store exists but can't be read |

```python
from cookietuner import CaptureIncomplete, CaptureTimeout, capture

try:
    cookies = capture(
        url="https://example.com/login",
        until={"session_id"},
        timeout=120,
    )
except CaptureTimeout as exc:
    print(f"gave up: {exc}")
except CaptureIncomplete as exc:
    print(f"browser closed too soon: {exc}")
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
