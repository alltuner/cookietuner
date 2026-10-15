# ABOUTME: Turns what a browser says it is into the headers it sends
# ABOUTME: Builds the sec-ch-ua* client hints and Accept-Language, as Chrome does

from collections.abc import Iterable
from typing import Any

# Asked of the page the capture opened, because the user-agent metadata API
# only exists in a secure context, so there is no browser-wide way to read it.
# getHighEntropyValues answers with brands, mobile and platform as well as what
# it was asked for, so one call covers both sets of hints. A page outside a
# secure context has no metadata to give and answers null. The URL comes back
# because it is what tells a page that has loaded from the empty document a
# window opens with.
IDENTITY_SCRIPT = """(async () => {
  const data = navigator.userAgentData;
  return {
    metadata: data
      ? await data.getHighEntropyValues([
          "architecture",
          "bitness",
          "fullVersionList",
          "model",
          "platformVersion",
        ])
      : null,
    languages: navigator.languages,
    href: location.href,
  };
})()"""

# Every high-entropy hint Chrome has, and the metadata it comes from.
HIGH_ENTROPY = {
    "sec-ch-ua-platform-version": "platformVersion",
    "sec-ch-ua-arch": "architecture",
    "sec-ch-ua-bitness": "bitness",
    "sec-ch-ua-model": "model",
}


def client_hints(metadata: dict[str, Any] | None) -> dict[str, str]:
    """The three hints Chrome puts on every request to a secure origin.

    Args:
        metadata: What ``navigator.userAgentData`` reported, or None if the
                  page had none to give.
    """
    if not metadata:
        return {}
    hints: dict[str, str] = {}
    if "brands" in metadata:
        hints["sec-ch-ua"] = _brands(metadata["brands"])
    if "mobile" in metadata:
        hints["sec-ch-ua-mobile"] = "?1" if metadata["mobile"] else "?0"
    if "platform" in metadata:
        hints["sec-ch-ua-platform"] = _quoted(metadata["platform"])
    return hints


def high_entropy_hints(metadata: dict[str, Any] | None) -> dict[str, str]:
    """The hints a site only receives if it asks for them, with ``Accept-CH``.

    Args:
        metadata: What ``navigator.userAgentData`` reported, or None if the
                  page had none to give.
    """
    if not metadata:
        return {}
    hints: dict[str, str] = {}
    if "fullVersionList" in metadata:
        hints["sec-ch-ua-full-version-list"] = _brands(metadata["fullVersionList"])
    for header, key in HIGH_ENTROPY.items():
        if key in metadata:
            hints[header] = _quoted(metadata[key])
    return hints


def accept_language(languages: Iterable[str]) -> str:
    """Renders the browser's languages the way Chrome's own header reads.

    The first language carries no quality, since q=1 is implied, and each one
    after it drops by a tenth and never goes below 0.1.
    """
    rendered: list[str] = []
    quality = 10
    for language in languages:
        rendered.append(language if not rendered else f"{language};q=0.{quality}")
        quality = max(quality - 1, 1)
    return ",".join(rendered)


def _brands(brands: list[dict[str, str]]) -> str:
    """A brand list as a hint value, in the order the browser gave it.

    Chrome permutes its own brands on every launch, deliberately, so the order
    is part of what it sends rather than something to tidy up.
    """
    return ", ".join(
        f"{_quoted(brand['brand'])};v={_quoted(brand['version'])}" for brand in brands
    )


def _quoted(value: str) -> str:
    """A header value in the quotes a structured-field string needs."""
    return f'"{value}"'
