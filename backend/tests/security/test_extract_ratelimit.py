"""Verify that extract-from-images endpoint has rate limiting applied."""
from __future__ import annotations

from app.core.rate_limit import RateLimiter
from app.routers.product import extract_rate_limit_dependency


def test_extract_endpoint_has_rate_limiter() -> None:
    """The extract-from-images endpoint must use a gen-tier rate limiter."""
    # extract_rate_limit_dependency is a Depends(...) wrapping a RateLimiter
    # Verify it exists and is configured for the "gen" tier
    dep = extract_rate_limit_dependency
    assert dep is not None
    # The dependency's underlying callable should be a RateLimiter
    assert isinstance(dep.dependency, RateLimiter)
    assert dep.dependency.tier == "gen"
