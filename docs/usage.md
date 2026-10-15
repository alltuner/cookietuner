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

A capture finishes once **every** condition you gave holds at the same time.
Without any condition, it ends when you close the browser, and returns
everything set for the domains:

```bash
uvx cookietuner capture --url https://example.com/login -d example.com
```

While it waits, it prints what is still outstanding to stderr, updating as each
condition is met:

```
Waiting for: session_id, uid!=anon_*, URL */dashboard*
Waiting for: uid!=anon_*, URL */dashboard*
```

`--timeout` caps the wait (300 seconds by default):

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --timeout 120
```

#### A cookie name, or a glob

`--until` takes a cookie name and can repeat. It also accepts a glob, for names
a site generates per project or per tenant:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until 'sb-*-auth-token'
```

Quote the glob, or the shell will try to expand it. The wildcards are `*`, `?`
and `[seq]`, and matching is case-sensitive.

#### A session cookie that also exists anonymously

Many sites set their session cookie name for anonymous visitors too, with a
different value. Waiting for the name alone finishes as the sign-in page loads,
before you have signed in. `--until-value` waits on the value instead:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until-value 'uid!=anon_*'
```

`name!=glob` waits until the cookie exists and stops matching; `name=glob` waits
until it exists and matches. The cookie has to exist either way, so this can't
be satisfied by it being absent.

#### Chunked cookies

Some auth libraries split a cookie too big for one header into `name.0`,
`name.1`, … (Supabase's SSR helpers do this above about 4 KB). `--until name`
matches a complete set as well as a plain cookie, so you ask for the name you
know:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until 'sb-*-auth-token' --settle 2 -o json
```

Nothing in a cookie says how many chunks there will be, so a set counts as
complete as soon as it has `.0`. That is what `--settle` is for: it keeps
polling for the given number of seconds after everything holds, so a trailing
chunk still lands. The cookies come back exactly as the browser had them, in
chunks; `join_chunks` in the [Python API](api.md#join_chunks) puts the value
back together.

#### Waiting on a URL

`--until-url` waits for an open page's URL to match a glob, which is often the
clearest signal that a sign-in finished:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until-url '*/dashboard*'
```

With a leading `!` it waits until no open page matches, for a sign-in that
redirects somewhere you can't predict:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until-url '!*/login*'
```

!!! note "URLs are never printed"
    A sign-in redirect can carry tokens in its query string or fragment, so
    progress lines and error messages name the pattern you gave, never the
    page the browser is on.

#### More than one domain

`-d` repeats, for a sign-in that sets cookies on several domains (an SSO hop, or
a site plus its custom domain). Each cookie keeps its own domain in the output:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com -d auth.example.com --until session_id -o json
```

Without `-d`, every domain the session touched is returned. Matching stays
exact, as in `cookies`: a subdomain needs naming in full. If a cookie you asked
for turns up on a domain you didn't name, the error says so instead of just
running out the clock.

#### Everything at once

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com -d auth.example.com \
  --until session_id --until 'sb-*-auth-token' \
  --until-value 'uid!=anon_*' \
  --until-url '*/dashboard*' \
  --settle 2 -o json
```

### Closing the window, or quitting Chrome

Closing the last window, quitting Chrome with Cmd+Q and Chrome exiting on its
own all mean the same thing: the capture keeps the last snapshot it took before
the end, so cookies set during the sign-in aren't lost either way.

If you gave conditions and that snapshot doesn't satisfy them, the capture fails
with `CaptureIncomplete` (exit code 4) and names what was still outstanding,
rather than handing you a half-signed-in session. The temporary profile is
deleted either way.

Exit codes let a script tell the failures apart: 3 timed out, 4 the browser
ended too early, 5 no Chrome, 6 the profile folder couldn't be read, 7 the
Passwords extension isn't installed. 2 means an option was wrong.

### Signing in from the Passwords app

`--passwords` loads Apple's iCloud Passwords extension into the temporary
profile, so you can sign in from the Passwords app (saved passwords,
verification codes, passkeys) instead of typing:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --passwords
```

The extension is copied from the one already installed in your own Chrome, so
install it there first. Its native helper only talks to the extension's Web
Store identity, which the copy keeps.

!!! note "Pairing happens every time"
    The profile is new on every capture, so the extension asks to pair with the
    Passwords app each run. That's the cost of leaving nothing behind.

#### The access `--passwords` needs

This is the only part of `capture` that reads your Chrome profile folder, to
copy the extension out of it. macOS withholds that folder until the program
running cookietuner has Full Disk Access, and a capture that can't read it fails
with:

```
Error: Chrome's profile folder is unreadable: ...
```

That's `ProfileAccessDenied`, exit code 6. To fix it, open **System Settings >
Privacy & Security > Full Disk Access** and grant it to the terminal or app
cookietuner runs under, then try again. It is a different failure from the
extension simply not being installed (`PasswordsExtensionMissing`, exit code 7),
which Full Disk Access won't help with.

Capturing without `--passwords` needs no access to the folder at all, so if you
only need the cookies, drop the flag.

### Through a proxy

`--proxy` routes the browser's traffic elsewhere, so the session originates from
another network. WebRTC is also stopped from reaching the network directly, so it
can't expose the local address the proxy is there to hide:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --proxy socks5://127.0.0.1:1080
```

### Reusing a session somewhere else

Cookies alone are only half of a session. Sites bind one to the browser that
signed in, and a request that arrives with the right cookies but a different
user agent is what they look for to spot a stolen one. `--identity` prints the
browser along with the cookies, so the session can be replayed as the browser
that opened it:

```bash
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until session_id -o json --identity
```

```json
{
  "cookies": [
    {
      "domain": "example.com",
      "name": "session_id",
      "value": "s3cr3t",
      "path": "/",
      "is_secure": true,
      "is_httponly": true,
      "is_expired": false
    }
  ],
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
  "client_hints": {
    "sec-ch-ua": "\"Google Chrome\";v=\"155\", \"Chromium\";v=\"155\", \"Not(A:Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"macOS\""
  },
  "high_entropy_hints": {
    "sec-ch-ua-full-version-list": "\"Google Chrome\";v=\"155.0.8059.79\", \"Chromium\";v=\"155.0.8059.79\", \"Not(A:Brand\";v=\"24.0.0.0\"",
    "sec-ch-ua-platform-version": "\"27.0.1\"",
    "sec-ch-ua-arch": "\"arm\"",
    "sec-ch-ua-bitness": "\"64\"",
    "sec-ch-ua-model": "\"\""
  },
  "accept_language": "en-GB,en-US;q=0.9,en;q=0.8",
  "final_url": "https://example.com/dashboard"
}
```

Without `--identity`, the output stays the plain list of cookies it has always
been. The identity is only printed as JSON, so `--identity` with a table says
so and does nothing.

From Python, `capture_session` returns the same thing as a `CapturedSession`,
and `headers()` gives you the headers that browser sends on its own:

```python
import requests

from cookietuner import capture_session

session = capture_session(
    url="https://example.com/login",
    domains={"example.com"},
    until={"session_id"},
)

reuse = requests.Session()
reuse.headers.update(session.headers())   # user agent, language, sec-ch-ua*
for cookie in session.cookies:
    reuse.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)

reuse.get("https://example.com/api/me")
```

The client hints come from `navigator.userAgentData`, which a page only has in a
secure context. A sign-in page on plain `http` has none to give, so there the
hints come back empty and `headers()` is the user agent and the language, which
come from the browser itself. The high-entropy hints are kept apart because a
site only receives those when it asks for them with `Accept-CH`.

!!! note "`final_url` can carry a token"
    A sign-in redirect often puts one in its query string or fragment, so the
    URL is printed with the cookies on stdout and never in a progress line or
    an error message.

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

### From Python

Everything the command does is available as a function, with the same condition
syntax behind both. A predicate covers what the flags can't express:

```python
from cookietuner import capture, join_chunks

cookies = capture(
    url="https://example.com/login",
    domains={"example.com", "auth.example.com"},
    until=lambda cs: any(c.name == "uid" and not c.value.startswith("anon_") for c in cs),
    until_url="*/dashboard*",
    settle=2,
    on_progress=lambda pending: print("waiting for", pending),
)

token = join_chunks(cookies, "sb-abcdef-auth-token")
```

See the [API reference](api.md#capture) for every argument, `capture_async`,
`capture_session` and the exceptions.

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
  -d, --domain TEXT                    Keep only these exact domains (leading dot
                                       ignored); repeatable. Without it, every
                                       domain is kept
  --until TEXT                         Cookie name or glob to wait for; repeatable.
                                       A name also matches a complete chunk set
                                       (name.0, name.1, ...)
  --until-value TEXT                   Wait for a cookie's value: name=glob, or
                                       name!=glob to wait until it stops matching;
                                       repeatable. The cookie has to exist either way
  --until-url TEXT                     Wait for an open page's URL to match this
                                       glob, or, with a leading !, until no page
                                       matches it
  --settle FLOAT                       Seconds to keep polling after everything
                                       asked for is there, so late cookies and
                                       trailing chunks land [default: 0]
  -o, --output [table|short|line|json] Output format [default: table]
  --identity                           Also print the browser's user agent, client
                                       hints and language, so the session can be
                                       replayed as the browser that signed in
                                       (-o json)
  --timeout FLOAT                      Seconds before giving up [default: 300]
  --passwords                          Load Apple's iCloud Passwords extension, to
                                       sign in from the Passwords app
  --proxy TEXT                         Proxy for the browser, e.g. socks5://127.0.0.1:1080
  --help                               Show this message and exit.
```

Exit codes: 0 success, 2 a bad option, 3 timed out, 4 the browser ended before
the conditions held, 5 no Chrome, 6 Chrome's profile folder couldn't be read,
7 the iCloud Passwords extension isn't installed, 130 interrupted.

### profiles

```
Usage: cookietuner profiles [OPTIONS]

Options:
  -b, --browser [chrome|safari]  Filter by browser
  --help                         Show this message and exit.
```
