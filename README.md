# cookietuner

A command-line tool to extract and display cookies from macOS browsers.

## Installation

The easiest way to run cookietuner is with [uv](https://docs.astral.sh/uv/):

```bash
uvx cookietuner
```

Or install it permanently:

```bash
uv tool install cookietuner
```

## Usage

### List cookies

```bash
# Chrome cookies (browser is required)
cookietuner cookies -b chrome

# Safari cookies
cookietuner cookies -b safari

# Filter by domain
cookietuner cookies -b chrome -d google.com

# Use a specific Chrome profile
cookietuner cookies -b chrome -p "Profile 1"
```

### Output formats

```bash
# Full table with all details (default)
cookietuner cookies -b chrome -o table

# Short table with just domain, name, value
cookietuner cookies -b chrome -o short

# Space-separated line format (for scripting)
cookietuner cookies -b chrome -o line

# JSON output
cookietuner cookies -b chrome -o json
```

### List browser profiles

```bash
# List all profiles
cookietuner profiles

# Filter by browser
cookietuner profiles -b chrome
```

## Features

- **Chrome support**: Decrypts cookies using macOS Keychain, supports Chrome 130+ format
- **Safari support**: Parses the binary cookies format with SameSite detection
- **Multiple output formats**: table, short, and JSON
- **Domain filtering**: Filter cookies by partial domain match
- **Profile selection**: Choose which browser profile to read from
- **Cookie metadata**: Shows expiration, Secure, HttpOnly, and SameSite flags

## Requirements

- macOS (the tool only works on macOS)
- Python 3.14+
- Chrome and/or Safari browser

## Development

```bash
# Clone the repository
git clone https://github.com/alltuner/cookietuner.git
cd cookietuner

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run the CLI
uv run cookietuner
```

## License

MIT
