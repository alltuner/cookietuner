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

Use `-d` or `--domain` to filter cookies by domain (partial match):

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
  -d, --domain TEXT                   Filter by domain (partial match)
  -p, --profile TEXT                  Browser profile name [default: Default]
  -o, --output [table|short|line|json] Output format [default: table]
  --help                              Show this message and exit.
```

### profiles

```
Usage: cookietuner profiles [OPTIONS]

Options:
  -b, --browser [chrome|safari]  Filter by browser
  --help                         Show this message and exit.
```
