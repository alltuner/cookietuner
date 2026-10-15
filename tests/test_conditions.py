# ABOUTME: Tests for deciding when a sign-in capture has what it was asked for
# ABOUTME: Covers name globs, chunk sets, value and URL conditions, and pending text

import pytest

from cookietuner.conditions import (
    Conditions,
    build,
    join_chunks,
    parse_url_condition,
    parse_value_condition,
)
from cookietuner.models import Cookie


def cookie(name: str, value: str = "v", domain: str = "example.com") -> Cookie:
    return Cookie(domain=domain, name=name, value=value, path="/")


def test_a_plain_name_is_met_by_that_cookie() -> None:
    conditions = build(until={"session_id"}, until_values=None, until_url=None)
    assert conditions.pending([cookie("session_id")], []) == []
    assert conditions.pending([cookie("other")], []) == ["session_id"]


def test_every_condition_has_to_hold_at_once() -> None:
    """Conditions are ANDed, so a half-finished sign-in keeps waiting."""
    conditions = build(
        until={"session_id"}, until_values=["uid!=anon_*"], until_url="*/dashboard*"
    )
    cookies = [cookie("session_id"), cookie("uid", "real_42")]

    assert conditions.pending(cookies, ["https://example.com/login"]) == [
        "URL */dashboard*"
    ]
    assert conditions.pending(cookies, ["https://example.com/dashboard"]) == []


def test_a_name_glob_matches_a_generated_cookie_name() -> None:
    conditions = build(until={"sb-*-auth-token"}, until_values=None, until_url=None)
    assert conditions.pending([cookie("sb-abcdef-auth-token")], []) == []
    assert conditions.pending([cookie("sb-auth-token-other")], []) == [
        "sb-*-auth-token"
    ]


def test_a_name_is_met_by_a_complete_chunk_set() -> None:
    """Auth libraries split a cookie over name.0, name.1, … above about 4 KB."""
    conditions = build(until={"auth-token"}, until_values=None, until_url=None)
    chunks = [cookie("auth-token.0", "aa"), cookie("auth-token.1", "bb")]
    assert conditions.pending(chunks, []) == []


def test_a_chunk_set_with_a_gap_is_not_complete() -> None:
    conditions = build(until={"auth-token"}, until_values=None, until_url=None)
    assert conditions.pending([cookie("auth-token.1")], []) == ["auth-token"]
    assert conditions.pending([cookie("auth-token.0"), cookie("auth-token.2")], []) == [
        "auth-token"
    ]


def test_a_lone_first_chunk_counts_as_a_complete_set() -> None:
    """Nothing in a cookie says how many chunks follow; --settle catches those."""
    conditions = build(until={"auth-token"}, until_values=None, until_url=None)
    assert conditions.pending([cookie("auth-token.0")], []) == []


def test_chunks_are_never_completed_across_domains() -> None:
    """A capture can span domains, and a split cookie never does.

    Neither domain holds a contiguous run, so pooling them must not invent one.
    """
    conditions = build(until={"auth-token"}, until_values=None, until_url=None)
    split = [
        cookie("auth-token.0", domain="example.com"),
        cookie("auth-token.2", domain="example.com"),
        cookie("auth-token.1", domain="auth.example.com"),
    ]
    assert conditions.pending(split, []) == ["auth-token"]


def test_a_value_condition_tells_a_signed_in_session_from_an_anonymous_one() -> None:
    conditions = build(until=None, until_values=["uid!=anon_*"], until_url=None)
    assert conditions.pending([cookie("uid", "anon_7")], []) == ["uid!=anon_*"]
    assert conditions.pending([cookie("uid", "real_42")], []) == []


def test_a_value_condition_needs_the_cookie_to_exist() -> None:
    """ "Not anonymous" must not be satisfied by the cookie being absent."""
    conditions = build(until=None, until_values=["uid!=anon_*"], until_url=None)
    assert conditions.pending([cookie("other")], []) == ["uid!=anon_*"]


def test_a_positive_value_condition_matches_the_pattern() -> None:
    conditions = build(until=None, until_values=["role=admin*"], until_url=None)
    assert conditions.pending([cookie("role", "member")], []) == ["role=admin*"]
    assert conditions.pending([cookie("role", "administrator")], []) == []


def test_a_url_condition_waits_for_the_page_to_arrive() -> None:
    conditions = build(until=None, until_values=None, until_url="*/dashboard*")
    assert conditions.pending([], ["https://example.com/login"]) == ["URL */dashboard*"]
    assert conditions.pending([], ["https://example.com/dashboard?welcome"]) == []


def test_a_negated_url_condition_waits_until_the_page_is_left() -> None:
    conditions = build(until=None, until_values=None, until_url="!*/login*")
    assert conditions.pending([], ["https://example.com/login"]) == ["URL not */login*"]
    assert conditions.pending([], ["https://example.com/dashboard"]) == []


def test_a_negated_url_condition_needs_a_page_to_be_open() -> None:
    """With no page loaded there is nothing to have left, so keep waiting."""
    conditions = build(until=None, until_values=None, until_url="!*/login*")
    assert conditions.pending([], []) == ["URL not */login*"]


def test_a_predicate_covers_what_the_declarative_forms_cannot() -> None:
    conditions = build(
        until=lambda cookies: len(cookies) > 1, until_values=None, until_url=None
    )
    assert conditions.pending([cookie("one")], []) == ["the given predicate"]
    assert conditions.pending([cookie("one"), cookie("two")], []) == []


def test_pending_names_patterns_and_never_values_or_urls() -> None:
    """A sign-in redirect can carry tokens, so only patterns may be printed."""
    conditions = build(
        until=None, until_values=["uid!=anon_*"], until_url="*/dashboard*"
    )

    pending = conditions.pending(
        [cookie("uid", "anon_s3cr3t")], ["https://example.com/cb#access_token=t0ken"]
    )

    assert pending == ["uid!=anon_*", "URL */dashboard*"]
    assert "s3cr3t" not in " ".join(pending)
    assert "t0ken" not in " ".join(pending)


def test_no_conditions_is_falsey() -> None:
    """Without conditions a capture ends when the browser does."""
    assert not build(until=None, until_values=None, until_url=None)
    assert not Conditions()
    assert build(until={"a"}, until_values=None, until_url=None)
    assert build(until=None, until_values=None, until_url="*/x*")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("uid=real_*", ("uid", "real_*", False)),
        ("uid!=anon_*", ("uid", "anon_*", True)),
        ("tok=a=b", ("tok", "a=b", False)),
    ],
)
def test_parsing_a_value_condition(text: str, expected: tuple[str, str, bool]) -> None:
    parsed = parse_value_condition(text)
    assert (parsed.name, parsed.pattern, parsed.negated) == expected


@pytest.mark.parametrize("text", ["uid", "", "=real_*", "uid=", "!=x"])
def test_a_malformed_value_condition_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_value_condition(text)


def test_an_empty_url_condition_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_url_condition("!")


def test_only_http_pages_count_towards_a_url_condition() -> None:
    """The --passwords flow starts on about:blank, which has left no login page."""
    conditions = build(until=None, until_values=None, until_url="!*/login*")
    assert conditions.pending([], ["about:blank"]) == ["URL not */login*"]
    assert conditions.pending([], ["chrome://new-tab-page"]) == ["URL not */login*"]


def test_join_chunks_reassembles_a_split_cookie() -> None:
    chunks = [
        cookie("auth-token.1", "second"),
        cookie("auth-token.0", "first"),
        cookie("other", "x"),
    ]
    assert join_chunks(chunks, "auth-token") == "firstsecond"


def test_join_chunks_prefers_a_cookie_of_that_exact_name() -> None:
    cookies = [cookie("auth-token", "whole"), cookie("auth-token.0", "part")]
    assert join_chunks(cookies, "auth-token") == "whole"


def test_join_chunks_returns_none_without_a_complete_set() -> None:
    assert join_chunks([cookie("other")], "auth-token") is None
    assert join_chunks([cookie("auth-token.1", "second")], "auth-token") is None


def test_join_chunks_refuses_to_splice_two_domains_together() -> None:
    """Concatenating across domains would yield a corrupt-looking credential."""
    split = [
        cookie("auth-token.0", "a", domain="example.com"),
        cookie("auth-token.0", "b", domain="auth.example.com"),
    ]
    with pytest.raises(ValueError, match="one domain"):
        join_chunks(split, "auth-token")


def test_join_chunks_accepts_the_same_value_on_two_domains() -> None:
    """A host and a domain cookie of one name is ordinary, not ambiguous."""
    same = [
        cookie("auth-token", "whole", domain="example.com"),
        cookie("auth-token", "whole", domain=".example.com"),
    ]
    assert join_chunks(same, "auth-token") == "whole"


def test_name_patterns_cover_names_and_value_conditions() -> None:
    """A fruitless wait points at cookies seen on a domain nobody asked for."""
    conditions = build(
        until={"session_id"}, until_values=["uid!=anon_*"], until_url=None
    )
    assert conditions.name_patterns() == frozenset({"session_id", "uid"})
