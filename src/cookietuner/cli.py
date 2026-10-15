# ABOUTME: Command-line interface using Typer
# ABOUTME: Provides commands to list, extract and capture browser cookies

import json
import sys
from enum import Enum
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import chrome, safari
from .capture import capture as capture_cookies
from .capture import capture_session
from .errors import CaptureError, CookieStoreUnreadable
from .models import CapturedSession, Cookie

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


def _show_pending(pending: list[str]) -> None:
    """Reports what a capture is still waiting for, as it changes.

    Escaped, because a glob like ``sb-[0-9]*`` would otherwise read as console
    markup. No cookie value or live URL ever reaches here.
    """
    if pending:
        messages.print(f"[cyan]Waiting for: {escape(', '.join(pending))}[/cyan]")
    else:
        messages.print("[cyan]Everything asked for is there.[/cyan]")


def _session_json(session: CapturedSession) -> dict[str, Any]:
    """The cookies and the browser that set them, as one object.

    The cookies keep the shape they have on their own, so a script reading
    them doesn't have to care which way the capture was asked for.
    """
    data = session.model_dump(mode="json")
    data["cookies"] = [
        cookie.model_dump(mode="json", exclude_none=True) for cookie in session.cookies
    ]
    return data


@app.command()
def capture(
    url: str = typer.Option(..., "--url", help="Page to open for signing in"),
    domain: list[str] = typer.Option(
        [],
        "--domain",
        "-d",
        help="Keep only these exact domains (leading dot ignored); repeatable. "
        "Without it, every domain is kept",
    ),
    until: list[str] = typer.Option(
        [],
        "--until",
        help="Cookie name or glob to wait for; repeatable. A name also matches "
        "a complete chunk set (name.0, name.1, ...)",
    ),
    until_value: list[str] = typer.Option(
        [],
        "--until-value",
        help="Wait for a cookie's value: name=glob, or name!=glob to wait until "
        "it stops matching; repeatable. The cookie has to exist either way",
    ),
    until_url: str | None = typer.Option(
        None,
        "--until-url",
        help="Wait for an open page's URL to match this glob, or, with a "
        "leading !, until no page matches it",
    ),
    settle: float = typer.Option(
        0.0,
        "--settle",
        help="Seconds to keep polling after everything asked for is there, so "
        "late cookies and trailing chunks land",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table, "--output", "-o", help="Output format"
    ),
    identity: bool = typer.Option(
        False,
        "--identity",
        help="Also print the browser's user agent, client hints and language, "
        "so the session can be replayed as the browser that signed in (-o json)",
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

    The capture finishes once every --until, --until-value and --until-url
    holds at the same time. Without any of them, it finishes when you close the
    browser.
    """
    messages.print("[cyan]Opening Chrome on a throwaway profile. Sign in there.[/cyan]")
    if not (until or until_value or until_url):
        messages.print("[cyan]Close the browser when you're done.[/cyan]")
        if settle:
            # Settling happens after the conditions hold, so with none given
            # there is nothing for it to wait after. Said out loud, because an
            # option that quietly does nothing is worse than one that complains.
            messages.print(
                "[yellow]--settle does nothing without --until, --until-value "
                "or --until-url to settle after.[/yellow]"
            )
    if passwords:
        messages.print(
            "[cyan]The Passwords extension needs pairing again, because the "
            "profile is new.[/cyan]"
        )
    show_identity = identity and output == OutputFormat.json
    if identity and not show_identity:
        # The identity is only ever printed as JSON, so asking for it in a
        # table would quietly do nothing.
        messages.print(
            "[yellow]--identity only prints with -o json, so it does nothing "
            "here.[/yellow]"
        )

    arguments: dict[str, Any] = {
        "url": url,
        "domains": domain,
        "until": set(until),
        "until_values": until_value,
        "until_url": until_url,
        "settle": settle,
        "timeout": timeout,
        "passwords": passwords,
        "proxy": proxy,
        "on_progress": _show_pending,
    }

    try:
        session = capture_session(**arguments) if show_identity else None
        cookie_list = (
            session.cookies if session is not None else capture_cookies(**arguments)
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except CaptureError as exc:
        messages.print(f"[red]Error: {escape(str(exc))}[/red]")
        raise typer.Exit(exc.exit_code) from exc
    except KeyboardInterrupt:
        messages.print("[yellow]Capture cancelled[/yellow]")
        raise typer.Exit(130) from None

    if session is not None:
        print(json.dumps(_session_json(session), indent=2))
        return
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
