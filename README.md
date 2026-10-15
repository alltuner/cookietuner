<p align="center">
  <img src="https://brand.alltuner.com/logos/cookietuner/horizontal.png" alt="cookietuner" width="500">
</p>

<p align="center">
  <strong>Extract and display cookies from macOS browsers.</strong><br>
  Decrypts Chrome's macOS Keychain entries, parses Safari's binary cookie store,
  and captures fresh sessions from a throwaway Chrome sign-in.
</p>

<p align="center">
  <a href="https://github.com/alltuner/cookietuner">GitHub</a> &middot;
  <a href="https://alltuner.com/sponsor">Sponsor</a>
</p>

<p align="center">
  <img src="https://img.shields.io/pypi/v/cookietuner?color=5B2333" alt="PyPI">
  <img src="https://img.shields.io/github/license/alltuner/cookietuner?color=5B2333" alt="License">
  <img src="https://img.shields.io/github/stars/alltuner/cookietuner?color=5B2333" alt="Stars">
</p>

---

## Get Started

Run without installing:

```bash
uvx cookietuner
```

Or install permanently:

```bash
uv tool install cookietuner
```

---

## What is cookietuner?

A command-line tool that reads cookies straight from your local macOS browser stores. It decrypts Chrome's encrypted cookie database via the macOS Keychain (Chrome 130+ format) and parses Safari's binary `Cookies.binarycookies` file directly, with no extensions involved.

When a store can't give you what you need, `cookietuner capture` opens a clean Chrome window instead, waits while you sign in yourself, and keeps the cookies that session set.

### Features

- **Chrome support** — decrypts cookies using macOS Keychain, Chrome 130+ format.
- **Safari support** — parses the binary cookies format with SameSite detection.
- **Throwaway sign-in capture** — a fresh Chrome profile, deleted afterwards, for session and HttpOnly cookies that never reach disk.
- **Flexible completion conditions** — finish on cookie names or globs, on a cookie's value, on the page URL, or on your own predicate, with a settle window for cookies that arrive late.
- **Chunked cookies** — matches a cookie split into `name.0`, `name.1`, … and reassembles it on request.
- **Sign in from the Passwords app** — optionally loads Apple's iCloud Passwords extension, so nothing is typed.
- **Multiple output formats** — table, short, line, and JSON.
- **Domain filtering** — filter by exact domain (`x.com` matches `.x.com`, not `api.x.com` or `dropbox.com`), several at once when capturing.
- **Profile selection** — choose which browser profile to read from.
- **Cookie metadata** — expiration, Secure, HttpOnly, and SameSite flags.
- **Python API** — `capture` and `capture_async`, with an exception and exit code per failure.

## Usage

### List cookies

```bash
# Chrome cookies (browser flag is required)
cookietuner cookies -b chrome

# Safari cookies
cookietuner cookies -b safari

# Filter by domain
cookietuner cookies -b chrome -d google.com

# Pick a Chrome profile
cookietuner cookies -b chrome -p "Profile 1"
```

### Output formats

| Format  | Flag       | Use case                              |
|---------|------------|---------------------------------------|
| Full table (default) | `-o table` | Browsing all cookie details          |
| Short table | `-o short` | Just domain, name, value             |
| Line | `-o line`  | Space-separated, for shell scripting |
| JSON | `-o json`  | Piping into `jq` or another tool     |

### Capture a fresh session

Opens Chrome on a temporary profile with none of your history or logins. You sign in by hand; cookietuner never types, fills or sees your credentials. The profile is deleted when the capture ends, including on timeout, Ctrl-C or error.

```bash
# Wait for specific cookies, then print them and close the browser
cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --until csrf_token -o json

# Without any condition, the capture ends when you close the browser
cookietuner capture --url https://example.com/login -d example.com

# Sign in from the Passwords app instead of typing
cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --passwords

# Route the session through a proxy
cookietuner capture --url https://example.com/login \
  -d example.com --proxy socks5://127.0.0.1:1080
```

#### Deciding when it's done

A capture finishes once every condition you gave holds at the same time. Without any, it ends when you close the browser.

| Option | Waits for |
|---|---|
| `--until name` | A cookie name, a glob (`--until 'sb-*-auth-token'`), or a complete chunk set (`name.0`, `name.1`, …). Repeatable |
| `--until-value 'uid!=anon_*'` | A cookie to exist and its value to match, or with `!=` to stop matching. Repeatable. This is what tells a signed-in session from an anonymous one that reuses the name |
| `--until-url '*/dashboard*'` | An open page's URL to match; with a leading `!`, for no page to match, so you can wait to leave `/login` |
| `--settle 2` | Keeps polling for 2 more seconds once everything holds, so late cookies, trailing chunks and post-login redirects land |
| `--timeout 120` | Caps the whole wait (300 seconds by default) |

`-d` repeats too, for a sign-in that spans domains:

```bash
cookietuner capture --url https://example.com/login \
  -d example.com -d auth.example.com \
  --until 'sb-*-auth-token' --until-value 'uid!=anon_*' \
  --until-url '*/dashboard*' --settle 2 -o json
```

Closing the window, quitting Chrome with Cmd+Q and Chrome exiting on its own all mean the same thing: the capture keeps the last snapshot taken before the end. If conditions were given and that snapshot doesn't satisfy them, it fails and names what was missing rather than returning a half-signed-in session. What it's still waiting for is printed to stderr as it goes, and values and live URLs never are.

Cookie values go to stdout on their own and progress goes to stderr, so the output pipes straight into a secret store:

```bash
cookietuner capture --url https://example.com/login \
  -d example.com --until session_id -o json | my-secret-store put example-session
```

This reaches cookies a store reader can't: session cookies, cookies kept only in memory, and HttpOnly cookies on a macOS version that denies access to Chrome's own store.

> **Note**
> `--passwords` is the only option that reads your Chrome profile folder, to copy the extension out of it. macOS withholds that folder until the program running cookietuner has Full Disk Access (System Settings > Privacy & Security), and without it the capture fails with `ProfileAccessDenied`. Capturing without `--passwords` needs no access at all.

### Use from Python

The same capture, as a function, with the same conditions behind both:

```python
from cookietuner import CaptureTimeout, capture, join_chunks

cookies = capture(
    url="https://example.com/login",
    domains={"example.com", "auth.example.com"},
    until={"sb-*-auth-token"},
    until_values=["uid!=anon_*"],
    until_url="*/dashboard*",
    settle=2,
    on_progress=lambda pending: print("waiting for", pending),
)

for cookie in cookies:                      # each a Cookie model
    print(cookie.domain, cookie.name, cookie.is_httponly)

token = join_chunks(cookies, "sb-abcdef-auth-token")
```

`until` also takes a predicate (`until=lambda cs: ...`), called on each poll with the cookies that would be returned, for anything the flags can't express. `capture_async` is the same function for an async application.

Failures raise `CaptureTimeout`, `CaptureIncomplete`, `ChromeNotFound`, `ProfileAccessDenied` or `PasswordsExtensionMissing`, all subclasses of `CaptureError`, each carrying the CLI's exit code as `exc.exit_code`. Full signatures, condition semantics and exit codes are in the [API reference](https://cookietuner.alltuner.com/api/).

### List browser profiles

```bash
# All profiles
cookietuner profiles

# Filter by browser
cookietuner profiles -b chrome
```

## Requirements

- macOS (the tool reads macOS-specific cookie stores).
- Python 3.11+.
- Chrome and/or Safari.

## Development

```bash
git clone https://github.com/alltuner/cookietuner.git
cd cookietuner
uv sync
uv run pytest
uv run cookietuner
```

## License

[MIT](LICENSE)

## Support the project

cookietuner is an open source project built by [David Poblador i Garcia](https://davidpoblador.com/) through [All Tuner Labs](https://www.alltuner.com/).

If this project was useful to you, [consider supporting its development](https://alltuner.com/sponsor).

---

<p align="center">
  Built by <a href="https://davidpoblador.com">David Poblador i Garcia</a> with the support of <a href="https://alltuner.com">All Tuner Labs</a>.<br>
  Made with ❤️ in Poblenou, Barcelona.
</p>
