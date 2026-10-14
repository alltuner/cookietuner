# Usage

## Listing cookies

The `cookies` command extracts cookies from a browser. The browser flag is required.

### Basic usage

=== "Chrome"

    ```bash
    uvx cookietuner cookies -b chrome
    ```

=== "Safari"

    ```bash
    uvx cookietuner cookies -b safari
    ```

### Filter by domain

Use `-d` or `--domain` to filter cookies by exact domain. A leading dot is ignored and subdomains are not included (`-d x.com` returns `.x.com` cookies but not `api.x.com` or `dropbox.com`):

```bash
uvx cookietuner cookies -b chrome -d google.com
```

### Select a Chrome profile

Chrome supports multiple profiles. Use `-p` or `--profile` to select one:

```bash
# List available profiles first
uvx cookietuner profiles -b chrome

# Then use a specific profile
uvx cookietuner cookies -b chrome -p "Profile 1"
```

## Output formats

Use `-o` or `--output` to change the output format.

### Table (default)

Full table with all cookie details:

```bash
uvx cookietuner cookies -b chrome -o table
```

Shows: Domain, Name, Value, Expires, Flags (Secure, HttpOnly, SameSite)

### Short

Compact table with essential info only:

```bash
uvx cookietuner cookies -b chrome -o short
```

Shows: Domain, Name, Value

### Line

Space-separated format, one cookie per line (full value, no truncation):

```bash
uvx cookietuner cookies -b chrome -o line
```

Output format: `domain name value`

!!! tip "Scripting"
    The line format is useful for shell scripting:
    ```bash
    uvx cookietuner cookies -b chrome -d github.com -o line | while read domain name value; do
      echo "Cookie: $name = $value"
    done
    ```

### JSON

Machine-readable JSON output:

```bash
uvx cookietuner cookies -b chrome -o json
```

Example output:

```json
[
  {
    "domain": ".github.com",
    "name": "logged_in",
    "value": "yes",
    "path": "/",
    "expires": "2027-01-27T12:00:00Z",
    "is_secure": true,
    "is_httponly": true,
    "same_site": "lax",
    "is_expired": false
  }
]
```

!!! tip "Piping JSON"
    Combine with `jq` for filtering:
    ```bash
    uvx cookietuner cookies -b chrome -d github.com -o json | jq '.[].value'
    ```

## Capturing a fresh session

Reading an everyday browser profile has limits. Session cookies and cookies kept
only in memory never reach disk, recent macOS versions can deny access to
Chrome's cookie store altogether, and what you need is mixed in with your whole
browsing life.

The `capture` command sidesteps all three. It opens Google Chrome on a brand new
temporary profile, with none of your history or logins, and waits while you sign
in yourself. cookietuner never types, fills or sees your credentials.

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --until csrf_token -o json
```

When the cookies you named exist, they're printed and the browser closes.

### Deciding when a capture is done

Use `--until` for each cookie name you need; it can repeat. Without it, the
capture ends when you close the last window, and returns everything set for the
domain:

```bash
uvx cookietuner capture --url https://example.com/login -d example.com
```

`--timeout` caps the wait (300 seconds by default):

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --timeout 120
```

### Through a proxy

`--proxy` routes the browser's traffic elsewhere, so the session originates from
another network. WebRTC is also stopped from reaching the network directly, so it
can't expose the local address the proxy is there to hide:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --proxy socks5://127.0.0.1:1080
```

### Piping into a secret store

Cookie values go to stdout on their own; progress and errors go to stderr. The
output pipes straight into a secret store, and no cookie value is ever logged:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until session_id -o json | my-secret-store put example-session
```

!!! note "The temporary profile is always removed"
    The profile folder is deleted when the capture ends, whether it succeeded,
    timed out, was interrupted with Ctrl-C or failed. A fresh one is created
    every time, so each capture is a separate sign-in.

## Listing profiles

The `profiles` command shows available browser profiles:

```bash
# All browsers
uvx cookietuner profiles

# Specific browser
uvx cookietuner profiles -b chrome
```

## Command reference

### cookies

```
Usage: cookietuner cookies [OPTIONS]

Options:
  -b, --browser [chrome|safari]       Browser to extract from (required)
  -d, --domain TEXT                   Filter by exact domain (leading dot ignored)
  -p, --profile TEXT                  Browser profile name [default: Default]
  -o, --output [table|short|line|json] Output format [default: table]
  --help                              Show this message and exit.
```

### capture

```
Usage: cookietuner capture [OPTIONS]

Options:
  --url TEXT                           Page to open for signing in (required)
  -d, --domain TEXT                    Keep only this exact domain (leading dot ignored)
  --until TEXT                         Cookie name to wait for; repeatable. Without
                                       it, waits for the window to close
  -o, --output [table|short|line|json] Output format [default: table]
  --timeout FLOAT                      Seconds before giving up [default: 300]
  --proxy TEXT                         Proxy for the browser, e.g. socks5://127.0.0.1:1080
  --help                               Show this message and exit.
```

### profiles

```
Usage: cookietuner profiles [OPTIONS]

Options:
  -b, --browser [chrome|safari]  Filter by browser
  --help                         Show this message and exit.
```
