# ABOUTME: Command-line interface using Typer
# ABOUTME: Provides commands to list, extract and capture browser cookies

import json
import sys
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table

from . import chrome, safari
from .capture import capture as capture_cookies
from .errors import CaptureError, CookieStoreUnreadable
from .models import Cookie

app = typer.Typer(
    help="Extract cookies from your browsers",
    no_args_is_help=True,
    # Frame locals hold cookie values and Chrome's decryption key, so a crash
    # must not print them.
    pretty_exceptions_show_locals=False,
)
console = Console()
# Cookie values go to stdout on their own, so everything else goes to stderr
# and piping straight into a secret store stays safe.
messages = Console(stderr=True)


def _check_macos() -> None:
    """Ensure we're running on macOS."""
    if sys.platform != "darwin":
        messages.print("[red]Error: cookietuner only supports macOS[/red]")
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
    line = "line"
    json = "json"


def _render(cookie_list: list[Cookie], output: OutputFormat) -> None:
    """Writes cookies to stdout in the requested format."""
    if not cookie_list:
        if output == OutputFormat.json:
            print("[]")
        elif output != OutputFormat.line:
            messages.print("[yellow]No cookies found[/yellow]")
        return

    if output == OutputFormat.json:
        data = [c.model_dump(mode="json", exclude_none=True) for c in cookie_list]
        print(json.dumps(data, indent=2))
        return

    if output == OutputFormat.line:
        for cookie in cookie_list:
            print(f"{cookie.domain} {cookie.name} {cookie.value}")
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
def cookies(
    browser: Browser = typer.Option(
        ..., "--browser", "-b", help="Browser to extract from"
    ),
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Filter by exact domain (leading dot ignored)"
    ),
    profile: str = typer.Option(
        "Default", "--profile", "-p", help="Browser profile name"
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table, "--output", "-o", help="Output format"
    ),
) -> None:
    """List cookies from a browser."""
    try:
        if browser == Browser.chrome:
            cookie_list = chrome.get_cookies(domain=domain, profile=profile)
        elif browser == Browser.safari:
            cookie_list = safari.get_cookies(domain=domain)
    except CookieStoreUnreadable as exc:
        messages.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc

    _render(cookie_list, output)


@app.command()
def capture(
    url: str = typer.Option(..., "--url", help="Page to open for signing in"),
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Keep only this exact domain (leading dot ignored)"
    ),
    until: list[str] = typer.Option(
        [],
        "--until",
        help="Cookie name to wait for; repeatable. Without it, waits for the "
        "window to close",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table, "--output", "-o", help="Output format"
    ),
    timeout: float = typer.Option(300.0, "--timeout", help="Seconds before giving up"),
    passwords: bool = typer.Option(
        False,
        "--passwords",
        help="Load Apple's iCloud Passwords extension, to sign in from the "
        "Passwords app instead of typing",
    ),
    proxy: str | None = typer.Option(
        None, "--proxy", help="Proxy for the browser, e.g. socks5://127.0.0.1:1080"
    ),
) -> None:
    """Sign in to a site in a throwaway Chrome window and keep its cookies.

    Chrome opens on a fresh profile with none of your history or logins. You
    sign in yourself; cookietuner never types or reads your credentials. The
    profile is deleted when the capture ends.
    """
    waiting_for = ", ".join(until) if until else "the window to close"
    messages.print(
        f"[cyan]Opening Chrome on a throwaway profile. Sign in; waiting for "
        f"{waiting_for}.[/cyan]"
    )
    if passwords:
        messages.print(
            "[cyan]The Passwords extension needs pairing again, because the "
            "profile is new.[/cyan]"
        )

    try:
        cookie_list = capture_cookies(
            url=url,
            domain=domain,
            until=set(until) or None,
            timeout=timeout,
            passwords=passwords,
            proxy=proxy,
        )
    except CaptureError as exc:
        messages.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    except KeyboardInterrupt:
        messages.print("[yellow]Capture cancelled[/yellow]")
        raise typer.Exit(130) from None

    _render(cookie_list, output)


@app.command()
def profiles(
    browser: Browser | None = typer.Option(
        None, "--browser", "-b", help="Filter by browser"
    ),
) -> None:
    """List available browser profiles."""
    profile_list = []

    if browser is None or browser == Browser.chrome:
        try:
            profile_list.extend(chrome.list_profiles())
        except CookieStoreUnreadable as exc:
            messages.print(f"[yellow]Warning: {exc}[/yellow]")

    if browser is None or browser == Browser.safari:
        profile_list.extend(safari.list_profiles())

    if not profile_list:
        messages.print("[yellow]No profiles found[/yellow]")
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
