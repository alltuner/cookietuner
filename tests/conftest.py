# ABOUTME: Shared pytest setup for the cookietuner test suite
# ABOUTME: Decides whether the Chrome-driving tests open a window or run headless

import importlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Fetched this way because the package re-exports the capture function over its
# own module's name, so plain imports find the function, not the module whose
# chrome_arguments the fixture below stands in front of.
capture_module = importlib.import_module("cookietuner.capture")

HEADLESS_ENV = "COOKIETUNER_TEST_HEADLESS"


def wants_headless() -> bool:
    """Whether the Chrome-driving tests should run without a window.

    A visible window is what a capture really opens, so CI keeps testing that
    configuration. On a desktop it steals focus every time the suite runs, and
    none of these tests signs in by hand, so locally they run headless.

    Set COOKIETUNER_TEST_HEADLESS to 1 or 0 to force it either way, which is
    how you watch a browser test happen.
    """
    forced = os.environ.get(HEADLESS_ENV)
    if forced:
        return forced != "0"
    return not os.environ.get("CI")


@pytest.fixture(autouse=True)
def chrome_window(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Runs the Chrome that browser-marked tests launch headless, or not.

    Patched here rather than behind an option in the package: a switch anything
    could set would let it reach into the window people type passwords into,
    which is not a trade worth making for test comfort.
    """
    if request.node.get_closest_marker("browser") and wants_headless():
        windowed = capture_module.chrome_arguments

        def headless(*, chrome: Path, profile: Path, url: str, proxy: str | None):
            args = windowed(chrome=chrome, profile=profile, url=url, proxy=proxy)
            # Chrome takes the URL as its one positional argument, so switches
            # have to go in front of it.
            return [*args[:-1], "--headless=new", args[-1]]

        monkeypatch.setattr(capture_module, "chrome_arguments", headless)
    yield
