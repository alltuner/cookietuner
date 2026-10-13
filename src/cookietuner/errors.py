# ABOUTME: Errors shared by the cookie backends
# ABOUTME: Distinguishes a store we may not read from one that isn't there


class CookieStoreUnreadable(Exception):
    """A browser's cookie store exists but this process may not read it."""
