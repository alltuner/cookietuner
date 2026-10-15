# ABOUTME: Decides when a sign-in capture has gathered what it was asked for
# ABOUTME: Matches cookie names, chunk sets, values and page URLs by glob

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

from .models import Cookie

# Auth libraries that outgrow a cookie split it into name.0, name.1, … and
# expect the browser to hand all of them back together.
CHUNKED = re.compile(r"^(?P<base>.+)\.(?P<index>\d+)$")

# A URL condition only looks at pages someone could have signed in on. The
# --passwords flow opens about:blank, and Chrome's own tabs come and go; both
# would otherwise satisfy "has left the login page".
PAGE_SCHEMES = ("http://", "https://")


def join_chunks(cookies: list[Cookie], name: str) -> str | None:
    """Reassembles a cookie that was split into ``name.0``, ``name.1``, ….

    A cookie named exactly ``name`` wins, since a split cookie doesn't also
    exist whole. Chunks are joined in index order, per domain, and only when
    they run from ``.0`` without a gap.

    Returns:
        The value, or None if neither a whole cookie nor a complete set is there.

    Raises:
        ValueError: if the cookies given hold more than one value for ``name``,
                    which a capture over several domains can produce. Splicing
                    chunks across domains would yield a plausible-looking,
                    corrupt credential, so it is refused rather than guessed.
    """
    whole = {c.value for c in cookies if c.name == name}
    joined = whole or {
        "".join(chunks[index] for index in sorted(chunks))
        for chunks in _chunks_by_domain(cookies, name)
    }

    if not joined:
        return None
    if len(joined) > 1:
        raise ValueError(
            f"The cookies given hold {len(joined)} different values for "
            f"{name!r}; filter them to one domain before joining"
        )
    return joined.pop()


def _chunks_by_domain(cookies: list[Cookie], name: str) -> list[dict[int, str]]:
    """The complete chunk sets named ``name``, one dict per domain."""
    by_domain: dict[str, dict[int, str]] = {}
    for cookie in cookies:
        found = CHUNKED.match(cookie.name)
        if found and found["base"] == name:
            by_domain.setdefault(cookie.domain, {})[int(found["index"])] = cookie.value
    return [chunks for chunks in by_domain.values() if _contiguous(set(chunks))]


def _contiguous(indices: set[int]) -> bool:
    """True if ``indices`` runs from 0 with nothing missing."""
    return bool(indices) and indices == set(range(len(indices)))


def _chunked_names(cookies: list[Cookie]) -> set[str]:
    """The base names of the complete chunk sets among ``cookies``.

    A set that is still growing looks complete as soon as its chunks are
    contiguous, because nothing in a cookie says how many there will be.
    ``settle`` is what catches a trailing chunk.
    """
    indices: dict[tuple[str, str], set[int]] = {}
    for cookie in cookies:
        found = CHUNKED.match(cookie.name)
        if found:
            key = (cookie.domain, found["base"])
            indices.setdefault(key, set()).add(int(found["index"]))
    return {base for (_, base), got in indices.items() if _contiguous(got)}


@dataclass(frozen=True)
class ValueCondition:
    """A cookie that must exist, whose value must or must not match a glob."""

    name: str
    pattern: str
    negated: bool

    def __str__(self) -> str:
        return f"{self.name}{'!=' if self.negated else '='}{self.pattern}"

    def met(self, cookies: list[Cookie]) -> bool:
        matching = [c for c in cookies if fnmatchcase(c.name, self.name)]
        if not matching:
            return False
        if self.negated:
            return not any(fnmatchcase(c.value, self.pattern) for c in matching)
        return any(fnmatchcase(c.value, self.pattern) for c in matching)


@dataclass(frozen=True)
class UrlCondition:
    """A glob an open page's URL must, or must not, match."""

    pattern: str
    negated: bool

    def __str__(self) -> str:
        return f"URL {'not ' if self.negated else ''}{self.pattern}"

    def met(self, urls: list[str]) -> bool:
        pages = [u for u in urls if u.startswith(PAGE_SCHEMES)]
        if self.negated:
            # Leaving a page needs somewhere to have gone, so a browser showing
            # no page at all hasn't left anything yet.
            return bool(pages) and not any(fnmatchcase(u, self.pattern) for u in pages)
        return any(fnmatchcase(u, self.pattern) for u in pages)


def parse_value_condition(text: str) -> ValueCondition:
    """Reads ``name=pattern``, or ``name!=pattern`` to require no match.

    The split is on the first ``=``, so a pattern may contain more of them.

    Raises:
        ValueError: if there's no ``=``, or either side is empty.
    """
    name, separator, pattern = text.partition("=")
    negated = name.endswith("!")
    if negated:
        name = name[:-1]
    if not separator or not name or not pattern:
        raise ValueError(
            f"Expected a cookie value condition, name=pattern or "
            f"name!=pattern, with both sides filled in; got {text!r}"
        )
    return ValueCondition(name=name, pattern=pattern, negated=negated)


def parse_url_condition(text: str) -> UrlCondition:
    """Reads a URL glob, which a leading ``!`` negates.

    Raises:
        ValueError: if nothing is left to match on.
    """
    negated = text.startswith("!")
    pattern = text[1:] if negated else text
    if not pattern:
        raise ValueError(
            f"Expected a URL pattern, optionally prefixed with ! to wait until "
            f"no page matches; got {text!r}"
        )
    return UrlCondition(pattern=pattern, negated=negated)


@dataclass(frozen=True)
class Conditions:
    """What has to hold, all at once, for a capture to be done.

    Empty conditions are falsey, which is how a capture knows to wait for the
    browser to close instead.
    """

    names: frozenset[str] = frozenset()
    values: tuple[ValueCondition, ...] = ()
    url: UrlCondition | None = None
    predicate: Callable[[list[Cookie]], bool] | None = None

    def __bool__(self) -> bool:
        return bool(self.names or self.values or self.url or self.predicate)

    def name_patterns(self) -> frozenset[str]:
        """Every cookie name or glob these conditions mention.

        Used to point out a cookie that did arrive, on a domain nobody asked
        for, which is the likeliest reason for a fruitless wait.
        """
        return self.names | {condition.name for condition in self.values}

    def describe(self) -> list[str]:
        """Names every condition, in the order ``pending`` reports them.

        Nothing is evaluated, so this is what a capture can say before it has
        managed a single poll.
        """
        return [
            *sorted(self.names),
            *(str(condition) for condition in self.values),
            *([str(self.url)] if self.url is not None else []),
            *(["the given predicate"] if self.predicate is not None else []),
        ]

    def pending(self, cookies: list[Cookie], urls: list[str]) -> list[str]:
        """Names the conditions that don't hold yet.

        Only patterns are named, never a cookie value or a live URL: a cookie
        is a credential, and a sign-in redirect can carry tokens in its query
        string or fragment.
        """
        present = {cookie.name for cookie in cookies} | _chunked_names(cookies)
        met: list[bool] = [
            any(fnmatchcase(got, name) for got in present)
            for name in sorted(self.names)
        ]
        met += [condition.met(cookies) for condition in self.values]
        if self.url is not None:
            met.append(self.url.met(urls))
        if self.predicate is not None:
            met.append(bool(self.predicate(cookies)))

        # strict, so that a condition added to one of these and not the other
        # fails loudly instead of going unchecked.
        return [
            text for text, holds in zip(self.describe(), met, strict=True) if not holds
        ]


@dataclass
class Progress:
    """The last thing the browser told us, and what it leaves outstanding.

    Kept outside the polling loop so that a browser which goes away mid-poll,
    or a timeout, still has the latest snapshot to fall back on.
    """

    cookies: list[Cookie] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    # True once the conditions have held, even if settling is still going on.
    settling: bool = False
    # Wanted cookie names seen on domains that weren't asked for.
    elsewhere: dict[str, set[str]] = field(default_factory=dict)

    @property
    def satisfied(self) -> bool:
        return not self.pending


def build(
    *,
    until: Iterable[str] | Callable[[list[Cookie]], bool] | None,
    until_values: Iterable[str] | None,
    until_url: str | None,
) -> Conditions:
    """Turns capture's arguments into one set of conditions.

    Raises:
        ValueError: if ``until`` is a bare string, or a value or URL condition
                    is malformed.
    """
    names: frozenset[str] = frozenset()
    predicate: Callable[[list[Cookie]], bool] | None = None
    if isinstance(until, str):
        raise ValueError(
            f"until takes a set of cookie names or a predicate, not the single "
            f"string {until!r}; pass {{{until!r}}} to wait for that one cookie"
        )
    if isinstance(until, Iterable):
        names = frozenset(until)
    elif until is not None:
        predicate = until

    return Conditions(
        names=names,
        values=tuple(parse_value_condition(text) for text in until_values or ()),
        url=parse_url_condition(until_url) if until_url else None,
        predicate=predicate,
    )
