# Installation

## Recommended: uvx

The easiest way to run cookietuner is with [uv](https://docs.astral.sh/uv/):

```bash
uvx cookietuner
```

This downloads and runs cookietuner in an isolated environment without installing it permanently.

## Permanent installation

To install cookietuner as a tool:

```bash
uv tool install cookietuner
```

Then run it directly:

```bash
cookietuner cookies -b chrome
```

## From source

```bash
# Clone the repository
git clone https://github.com/yourusername/cookietuner.git
cd cookietuner

# Install dependencies
uv sync

# Run the CLI
uv run cookietuner
```

## Requirements

!!! warning "macOS only"
    cookietuner only works on macOS. It reads browser cookie databases that are specific to macOS file paths and encryption methods.

- macOS
- Python 3.14+
- Chrome and/or Safari browser installed
