# cookietuner

A command-line tool to extract and display cookies from macOS browsers.

## Features

- **Chrome support** - Decrypts cookies using macOS Keychain, supports Chrome 130+ format
- **Safari support** - Parses the binary cookies format with SameSite detection
- **Throwaway sign-in capture** - A fresh Chrome profile, deleted afterwards, for the session and HttpOnly cookies that never reach disk
- **Flexible completion conditions** - Finish on cookie names or globs, on a cookie's value, on the page URL, or on your own predicate, with a settle window for late cookies
- **Chunked cookies** - Matches a cookie split into `name.0`, `name.1`, … and reassembles it on request
- **Sign in from the Passwords app** - Optionally loads Apple's iCloud Passwords extension, so nothing is typed
- **Multiple output formats** - Table, short, line, and JSON
- **Domain filtering** - Filter cookies by exact domain (leading dot ignored, no subdomains), several at once when capturing
- **Profile selection** - Choose which browser profile to read from
- **Cookie metadata** - Shows expiration, Secure, HttpOnly, and SameSite flags
- **Python API** - `capture` and `capture_async`, with an exception and exit code per failure

## Quick start

```bash
# Read cookies from a browser store
uvx cookietuner cookies -b chrome -d github.com

# Or sign in to a throwaway Chrome window and keep that session
uvx cookietuner capture --url https://example.com/login \
  -d example.com --until-value 'uid!=anon_*' --until-url '*/dashboard*'
```

## Requirements

- macOS (the tool only works on macOS)
- Python 3.11+
- Chrome and/or Safari browser
