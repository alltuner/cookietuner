# ABOUTME: Exact domain matching for cookie filtering
# ABOUTME: Compares domains case-insensitively, ignoring the leading dot browsers store


def _normalize(domain: str) -> str:
    return domain.strip().lower().lstrip(".")


def domain_matches(cookie_domain: str, domain: str) -> bool:
    """Return True if a cookie's domain is exactly ``domain``.

    Browsers store domain cookies with a leading dot (``.x.com``) and
    host-only cookies without one (``x.com``); both count as ``x.com``.
    Subdomains and lookalikes (``api.x.com``, ``dropbox.com``) do not match.
    """
    return _normalize(cookie_domain) == _normalize(domain)
