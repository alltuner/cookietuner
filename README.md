<p align="center">
  <img src="https://brand.alltuner.com/logos/cookietuner/horizontal.png" alt="cookietuner" width="500">
</p>

<p align="center">
  <strong>Extract and display cookies from macOS browsers.</strong><br>
  Decrypts Chrome's macOS Keychain entries and parses Safari's binary cookie store.
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

A command-line tool that reads cookies straight from your local macOS browser stores. It decrypts Chrome's encrypted cookie database via the macOS Keychain (Chrome 130+ format) and parses Safari's binary `Cookies.binarycookies` file directly. No browser automation, no extensions.

### Features

- **Chrome support** — decrypts cookies using macOS Keychain, Chrome 130+ format.
- **Safari support** — parses the binary cookies format with SameSite detection.
- **Multiple output formats** — table, short, line, and JSON.
- **Domain filtering** — filter by partial domain match.
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

### List browser profiles

```bash
# All profiles
cookietuner profiles

# Filter by browser
cookietuner profiles -b chrome
```

## Requirements

- macOS (the tool reads macOS-specific cookie stores).
- Python 3.14+.
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
