"""
Tests for per-IP auth-endpoint rate limiting (issue: no throttle on
/auth/token, /auth/callback, PAT test/save).

Covers:
1. _AuthRateLimiter (the underlying sliding-window counter) in isolation.
2. Each of the four guarded endpoints returning 429 once a client IP is over
   the limit for that endpoint's bucket, and other IPs/buckets being
   unaffected.
"""
import time
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from auth import (
    _AuthRateLimiter,
    _enforce_auth_rate_limit,
    _get_client_ip,
    auth_rate_limiter,
    github_callback,
    github_token_login,
    save_github_token,
)
# Aliased: a bare "test_github_token" import is picked up by pytest's own
# test discovery (any top-level "test_*" callable), which tries to collect
# the endpoint function itself as a test case.
from auth import test_github_token as pat_test_endpoint


def _mock_request(client_ip: str = "203.0.113.5") -> Mock:
    request = Mock(spec=Request)
    request.headers = {"X-Forwarded-For": client_ip}
    # Real empty dict/None (not Mock's auto-generated attrs, which are
    # truthy) so extract_session_token() cleanly finds no session and the
    # PAT endpoints hit their real 401 path instead of an unrelated
    # AttributeError from db=None being queried.
    request.cookies = {}
    request.client = Mock()
    request.client.host = client_ip
    request.url = Mock()
    request.url.scheme = "https"
    return request


@pytest.fixture(autouse=True)
def reset_auth_rate_limiter():
    """Every test in this file gets a clean limiter, same idea as
    oauth_states._states.clear() elsewhere in the auth test suite."""
    auth_rate_limiter._hits.clear()
    yield
    auth_rate_limiter._hits.clear()


class TestGetClientIp:
    def test_prefers_x_forwarded_for(self):
        request = _mock_request("198.51.100.7")
        assert _get_client_ip(request) == "198.51.100.7"

    def test_takes_last_ip_in_forwarded_chain(self):
        """nginx appends via $proxy_add_x_forwarded_for, so the last entry is
        the one the trusted proxy added - the first is client-supplied and
        trivially spoofable to defeat the rate limiter."""
        request = _mock_request()
        request.headers = {"X-Forwarded-For": "198.51.100.7, 10.0.0.1"}
        assert _get_client_ip(request) == "10.0.0.1"

    def test_falls_back_to_request_client_host(self):
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.0.2.9"
        assert _get_client_ip(request) == "192.0.2.9"

    def test_falls_back_to_unknown_with_no_client(self):
        request = Mock(spec=Request)
        request.headers = {}
        request.client = None
        assert _get_client_ip(request) == "unknown"


class TestAuthRateLimiter:
    def test_allows_requests_up_to_the_limit(self):
        limiter = _AuthRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.check("bucket", "1.2.3.4") is True
        assert limiter.check("bucket", "1.2.3.4") is True
        assert limiter.check("bucket", "1.2.3.4") is True

    def test_rejects_once_over_the_limit(self):
        limiter = _AuthRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.check("bucket", "1.2.3.4") is True
        assert limiter.check("bucket", "1.2.3.4") is False
        # Still rejected, not accidentally counted/reset by the rejection itself.
        assert limiter.check("bucket", "1.2.3.4") is False

    def test_separate_ips_do_not_share_a_budget(self):
        limiter = _AuthRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("bucket", "1.2.3.4") is True
        assert limiter.check("bucket", "1.2.3.4") is False
        # A different IP has its own, unaffected budget.
        assert limiter.check("bucket", "5.6.7.8") is True

    def test_separate_buckets_do_not_share_a_budget(self):
        limiter = _AuthRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("auth_token", "1.2.3.4") is True
        assert limiter.check("auth_token", "1.2.3.4") is False
        # Same IP, different bucket - not blocked by the other bucket's use.
        assert limiter.check("pat_save", "1.2.3.4") is True

    def test_resets_after_the_window_elapses(self):
        limiter = _AuthRateLimiter(max_requests=1, window_seconds=0.1)
        assert limiter.check("bucket", "1.2.3.4") is True
        assert limiter.check("bucket", "1.2.3.4") is False
        time.sleep(0.15)
        assert limiter.check("bucket", "1.2.3.4") is True

    def test_cleanup_drops_keys_with_no_hits_left_in_window(self):
        limiter = _AuthRateLimiter(max_requests=5, window_seconds=0.1)
        limiter.check("bucket", "1.2.3.4")
        assert ("bucket", "1.2.3.4") in limiter._hits
        time.sleep(0.15)
        # A check for an unrelated key still triggers cleanup of the stale one.
        limiter.check("bucket", "9.9.9.9")
        assert ("bucket", "1.2.3.4") not in limiter._hits


class TestEnforceAuthRateLimit:
    def test_raises_429_with_safe_detail_once_over_limit(self):
        auth_rate_limiter.max_requests = 1
        try:
            request = _mock_request("203.0.113.9")
            _enforce_auth_rate_limit("some_bucket", request)  # 1st: allowed
            with pytest.raises(HTTPException) as exc_info:
                _enforce_auth_rate_limit("some_bucket", request)  # 2nd: rejected
            assert exc_info.value.status_code == 429
            assert "Too many requests" in exc_info.value.detail
        finally:
            auth_rate_limiter.max_requests = 20


class TestEndpointRateLimitWiring:
    """Each guarded endpoint checks the rate limit as its first action, so a
    tripped limiter raises 429 before touching auth/DB/GitHub at all - these
    calls intentionally pass dummy payload/db values that would fail later
    if the rate-limit check didn't short-circuit first."""

    def setup_method(self):
        auth_rate_limiter.max_requests = 1

    def teardown_method(self):
        auth_rate_limiter.max_requests = 20

    def test_github_callback_returns_429_over_limit(self):
        request = _mock_request("203.0.113.10")
        github_callback(code="c", state="s", request=request, db=None)  # 1st: consumes budget
        with pytest.raises(HTTPException) as exc_info:
            github_callback(code="c", state="s", request=request, db=None)
        assert exc_info.value.status_code == 429

    def test_github_token_login_returns_429_over_limit(self):
        request = _mock_request("203.0.113.11")
        payload = Mock(token="not-a-valid-token-format")
        try:
            github_token_login(payload=payload, request=request, response=Mock(), db=None)
        except HTTPException:
            pass  # may fail later validation - budget is still consumed first
        with pytest.raises(HTTPException) as exc_info:
            github_token_login(payload=payload, request=request, response=Mock(), db=None)
        assert exc_info.value.status_code == 429

    def test_test_github_token_returns_429_over_limit(self):
        request = _mock_request("203.0.113.12")
        payload = Mock(token="not-a-valid-token-format")
        try:
            pat_test_endpoint(username="someone", payload=payload, request=request, db=None)
        except HTTPException:
            pass
        with pytest.raises(HTTPException) as exc_info:
            pat_test_endpoint(username="someone", payload=payload, request=request, db=None)
        assert exc_info.value.status_code == 429

    def test_save_github_token_returns_429_over_limit(self):
        request = _mock_request("203.0.113.13")
        payload = Mock(token="not-a-valid-token-format")
        try:
            save_github_token(username="someone", payload=payload, request=request, db=None)
        except HTTPException:
            pass
        with pytest.raises(HTTPException) as exc_info:
            save_github_token(username="someone", payload=payload, request=request, db=None)
        assert exc_info.value.status_code == 429

    def test_different_ips_are_independent_across_endpoints(self):
        """Confirms buckets are actually per-endpoint: hammering one endpoint
        from one IP does not block a different IP calling a different
        endpoint."""
        auth_rate_limiter.max_requests = 1
        attacker = _mock_request("203.0.113.14")
        legit = _mock_request("203.0.113.15")

        github_callback(code="c", state="s", request=attacker, db=None)
        with pytest.raises(HTTPException):
            github_callback(code="c", state="s", request=attacker, db=None)

        # A different IP hitting the SAME endpoint is unaffected.
        result = github_callback(code="c", state="bad-state", request=legit, db=None)
        assert result == {"error": "Invalid or expired authentication request. Please try logging in again."}
