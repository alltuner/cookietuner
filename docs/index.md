# cookietuner

A command-line tool to extract and display cookies from macOS browsers.

## Features

- **Chrome support** - Decrypts cookies using macOS Keychain, supports Chrome 130+ format
- **Safari support** - Parses the binary cookies format with SameSite detection
- **Multiple output formats** - Table, short, and JSON
- **Domain filtering** - Filter cookies by partial domain match
- **Profile selection** - Choose which browser profile to read from
- **Cookie metadata** - Shows expiration, Secure, HttpOnly, and SameSite flags

## Quick start

```bash
uvx cookietuner cookies -b chrome -d github.com
```

## Requirements

- macOS (the tool only works on macOS)
- Python 3.14+
- Chrome and/or Safari browser
