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
- **Sign in from the Passwords app** — optionally loads Apple's iCloud Passwords extension, so nothing is typed.
- **Multiple output formats** — table, short, line, and JSON.
- **Domain filtering** — filter by exact domain (`x.com` matches `.x.com`, not `api.x.com` or `dropbox.com`).
- **Profile selection** — choose which browser profile to read from.
- **Cookie metadata** — expiration, Secure, HttpOnly, and SameSite flags.

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

# Without --until, the capture ends when you close the window
cookietuner capture --url https://example.com/login -d example.com

# Sign in from the Passwords app instead of typing
cookietuner capture --url https://example.com/login \
  -d example.com --until session_id --passwords

# Route the session through a proxy
cookietuner capture --url https://example.com/login \
  -d example.com --proxy socks5://127.0.0.1:1080
```

Cookie values go to stdout on their own and progress goes to stderr, so the output pipes straight into a secret store:

```bash
cookietuner capture --url https://example.com/login \
  -d example.com --until session_id -o json | my-secret-store put example-session
```

This reaches cookies a store reader can't: session cookies, cookies kept only in memory, and HttpOnly cookies on a macOS version that denies access to Chrome's own store.

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
