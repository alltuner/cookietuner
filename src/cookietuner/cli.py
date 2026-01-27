# ABOUTME: Command-line interface using Typer
# ABOUTME: Provides commands to list and extract browser cookies

import json
import sys
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table

from . import chrome, safari

app = typer.Typer(help="Extract cookies from your browsers", no_args_is_help=True)
console = Console()


def _check_macos() -> None:
    """Ensure we're running on macOS."""
    if sys.platform != "darwin":
        console.print("[red]Error: cookietuner only supports macOS[/red]")
        raise typer.Exit(1)


@app.callback()
def main_callback() -> None:
    """Check platform before running any command."""
    _check_macos()


class Browser(str, Enum):
    chrome = "chrome"
    safari = "safari"


class OutputFormat(str, Enum):
    table = "table"
    short = "short"
    json = "json"


@app.command()
def cookies(
    browser: Browser = typer.Option(
        ..., "--browser", "-b", help="Browser to extract from"
    ),
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Filter by domain (partial match)"
    ),
    profile: str = typer.Option(
        "Default", "--profile", "-p", help="Browser profile name"
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table, "--output", "-o", help="Output format"
    ),
) -> None:
    """List cookies from a browser."""
    if browser == Browser.chrome:
        cookie_list = chrome.get_cookies(domain=domain, profile=profile)
    elif browser == Browser.safari:
        cookie_list = safari.get_cookies(domain=domain)

    if not cookie_list:
        if output == OutputFormat.json:
            print("[]")
        else:
            console.print("[yellow]No cookies found[/yellow]")
        raise typer.Exit(0)

    if output == OutputFormat.json:
        data = [c.model_dump(mode="json", exclude_none=True) for c in cookie_list]
        print(json.dumps(data, indent=2))
        return

    if output == OutputFormat.short:
        table = Table(title=f"Cookies ({len(cookie_list)} found)")
        table.add_column("Domain", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Value", style="white", max_width=50, overflow="ellipsis")

        for cookie in cookie_list:
            value_display = (
                cookie.value[:47] + "..." if len(cookie.value) > 50 else cookie.value
            )
            table.add_row(cookie.domain, cookie.name, value_display)

        console.print(table)
        return

    table = Table(title=f"Cookies ({len(cookie_list)} found)")
    table.add_column("Domain", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Value", style="white", max_width=40, overflow="ellipsis")
    table.add_column("Expires", style="dim")
    table.add_column("Flags", style="yellow")

    for cookie in cookie_list:
        value_display = (
            cookie.value[:37] + "..." if len(cookie.value) > 40 else cookie.value
        )
        expires_display = (
            cookie.expires.strftime("%Y-%m-%d") if cookie.expires else "session"
        )

        flags = []
        if cookie.is_secure:
            flags.append("Secure")
        if cookie.is_httponly:
            flags.append("HttpOnly")
        if cookie.same_site:
            flags.append(f"SameSite={cookie.same_site}")
        flags_display = ", ".join(flags) if flags else "-"

        table.add_row(
            cookie.domain, cookie.name, value_display, expires_display, flags_display
        )

    console.print(table)


@app.command()
def profiles(
    browser: Browser | None = typer.Option(
        None, "--browser", "-b", help="Filter by browser"
    ),
) -> None:
    """List available browser profiles."""
    profile_list = []

    if browser is None or browser == Browser.chrome:
        profile_list.extend(chrome.list_profiles())

    if browser is None or browser == Browser.safari:
        profile_list.extend(safari.list_profiles())

    if not profile_list:
        console.print("[yellow]No profiles found[/yellow]")
        raise typer.Exit(0)

    title = (
        "Browser Profiles" if browser is None else f"{browser.value.title()} Profiles"
    )
    table = Table(title=title)
    table.add_column("Browser", style="cyan")
    table.add_column("Profile Name", style="green")
    table.add_column("Path", style="dim")

    for p in profile_list:
        table.add_row(p.browser.title(), p.profile_name, p.path)

    console.print(table)


def main() -> None:
    app()
