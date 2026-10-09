# ABOUTME: Tests for exact cookie domain matching
# ABOUTME: Ensures "x.com" never matches lookalike hosts such as dropbox.com

import pytest

from cookietuner.domain import domain_matches


@pytest.mark.parametrize(
    ("cookie_domain", "domain"),
    [
        ("x.com", "x.com"),
        (".x.com", "x.com"),
        ("x.com", ".x.com"),
        (".x.com", ".x.com"),
        (".X.com", "x.COM"),
        (".www.linkedin.com", "www.linkedin.com"),
    ],
)
def test_domain_matches_same_domain(cookie_domain: str, domain: str) -> None:
    assert domain_matches(cookie_domain, domain)


@pytest.mark.parametrize(
    ("cookie_domain", "domain"),
    [
        (".dropbox.com", "x.com"),
        ("netbox.com", "x.com"),
        ("api.x.com", "x.com"),
        (".www.linkedin.com", "linkedin.com"),
        ("x.com", "api.x.com"),
        ("x.com.evil.net", "x.com"),
    ],
)
def test_domain_matches_rejects_other_domains(cookie_domain: str, domain: str) -> None:
    assert not domain_matches(cookie_domain, domain)
