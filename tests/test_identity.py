# ABOUTME: Tests the headers built from what the capturing browser says it is
# ABOUTME: The samples are what a real Chrome reported and sent on the wire

from collections.abc import Callable
from typing import Any

import pytest

from cookietuner.identity import accept_language, client_hints, high_entropy_hints
from cookietuner.models import CapturedSession, Cookie

# What navigator.userAgentData.getHighEntropyValues answered in a capture
# window, alongside the headers that same browser put on its requests. The
# brand order is the browser's own: Chrome permutes it deliberately, so
# reordering it here would be a different fingerprint.
CHROME_METADATA: dict[str, Any] = {
    "architecture": "arm",
    "bitness": "64",
    "brands": [
        {"brand": "Google Chrome", "version": "155"},
        {"brand": "Chromium", "version": "155"},
        {"brand": "Not(A:Brand", "version": "24"},
    ],
    "fullVersionList": [
        {"brand": "Google Chrome", "version": "155.0.8059.79"},
        {"brand": "Chromium", "version": "155.0.8059.79"},
        {"brand": "Not(A:Brand", "version": "24.0.0.0"},
    ],
    "mobile": False,
    "model": "",
    "platform": "macOS",
    "platformVersion": "27.0.1",
}

SENT_ON_THE_WIRE = {
    "sec-ch-ua": '"Google Chrome";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)


def test_client_hints_are_the_headers_the_browser_sent() -> None:
    """The point of the whole feature: the hints have to match the wire."""
    assert client_hints(CHROME_METADATA) == SENT_ON_THE_WIRE


def test_client_hints_keep_the_brand_order_they_were_given() -> None:
    """Chrome permutes its brand list on purpose, so sorting it would lie."""
    reversed_brands = {**CHROME_METADATA, "brands": CHROME_METADATA["brands"][::-1]}

    assert client_hints(reversed_brands)["sec-ch-ua"] == (
        '"Not(A:Brand";v="24", "Chromium";v="155", "Google Chrome";v="155"'
    )


def test_a_phone_reports_itself_as_mobile() -> None:
    assert client_hints({**CHROME_METADATA, "mobile": True})["sec-ch-ua-mobile"] == "?1"


def test_high_entropy_hints_are_the_ones_a_site_has_to_ask_for() -> None:
    assert high_entropy_hints(CHROME_METADATA) == {
        "sec-ch-ua-full-version-list": (
            '"Google Chrome";v="155.0.8059.79", "Chromium";v="155.0.8059.79", '
            '"Not(A:Brand";v="24.0.0.0"'
        ),
        "sec-ch-ua-platform-version": '"27.0.1"',
        "sec-ch-ua-arch": '"arm"',
        "sec-ch-ua-bitness": '"64"',
        "sec-ch-ua-model": '""',
    }


@pytest.mark.parametrize("build", [client_hints, high_entropy_hints])
def test_a_page_that_could_not_answer_yields_no_hints(
    build: Callable[[dict[str, Any] | None], dict[str, str]],
) -> None:
    """An insecure page has no userAgentData, and Chrome sends it no hints."""
    assert build(None) == {}
    assert build({}) == {}


def test_a_hint_the_browser_left_out_is_left_out() -> None:
    """Only what the browser said, so a future Chrome can drop a hint."""
    assert "sec-ch-ua-model" not in high_entropy_hints(
        {key: value for key, value in CHROME_METADATA.items() if key != "model"}
    )


def test_accept_language_matches_what_the_browser_sent() -> None:
    """Chrome's own rendering: the first language is implicitly q=1."""
    assert accept_language(["en-GB", "en-US", "en"]) == "en-GB,en-US;q=0.9,en;q=0.8"


def test_accept_language_stops_dropping_the_quality_at_a_tenth() -> None:
    """Taken off the wire from a Chrome with a full language list."""
    languages = ["en-GB", "en-US", "en", "es-ES", "es", "ca", "fr", "de", "it", "pt"]

    assert accept_language(languages) == (
        "en-GB,en-US;q=0.9,en;q=0.8,es-ES;q=0.7,es;q=0.6,ca;q=0.5,fr;q=0.4,"
        "de;q=0.3,it;q=0.2,pt;q=0.1"
    )
    assert accept_language([*languages, "nl", "sv"]).endswith("nl;q=0.1,sv;q=0.1")


def test_one_language_needs_no_quality_at_all() -> None:
    assert accept_language(["en-GB"]) == "en-GB"


def test_headers_are_the_ones_a_browser_sends_unasked() -> None:
    """The high-entropy hints are left out: a site only gets those if it asks."""
    session = CapturedSession(
        cookies=[],
        user_agent=USER_AGENT,
        client_hints=client_hints(CHROME_METADATA),
        high_entropy_hints=high_entropy_hints(CHROME_METADATA),
        accept_language="en-GB,en-US;q=0.9,en;q=0.8",
    )

    assert session.headers() == {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        **SENT_ON_THE_WIRE,
    }


def test_headers_leave_out_what_the_browser_never_said() -> None:
    """A page that couldn't answer still leaves a usable user agent."""
    session = CapturedSession(cookies=[], user_agent=USER_AGENT)

    assert session.headers() == {"User-Agent": USER_AGENT}


def test_a_captured_session_keeps_its_cookies_as_they_were() -> None:
    cookie = Cookie(domain="example.com", name="session_id", value="s3cr3t", path="/")
    session = CapturedSession(cookies=[cookie], user_agent=USER_AGENT)

    assert session.cookies == [cookie]
    assert session.final_url is None
