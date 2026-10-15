# ABOUTME: Shared pytest setup for the cookietuner test suite
# ABOUTME: Decides whether the Chrome-driving tests open a window or run headless

import os
from collections.abc import Iterator

import pytest

from cookietuner.capture import EXTRA_ARGUMENTS_ENV

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
    """Runs the Chrome that browser-marked tests launch headless, or not."""
    if request.node.get_closest_marker("browser") and wants_headless():
        monkeypatch.setenv(EXTRA_ARGUMENTS_ENV, "--headless=new")
    else:
        # An inherited value would otherwise reach the tests that assert on
        # the command line Chrome is given.
        monkeypatch.delenv(EXTRA_ARGUMENTS_ENV, raising=False)
    yield
