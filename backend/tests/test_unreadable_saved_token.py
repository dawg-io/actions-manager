"""
A saved PAT that cannot be decrypted must not be handed out as a credential.

`_load_saved_personal_access_token` returns INVALID_SAVED_TOKEN_SENTINEL when
the stored ciphertext will not open — normally because SECRET_KEY changed since
it was written. The sentinel looks exactly like a PAT (`ghp_...`), so every
consumer of the credential store treated it as one and 401'd against GitHub.

That is #2050: after a container update every project showed "Needs Attention",
because the drift sweep ran with the sentinel and every read failed at once.
Session auth already rejected it; nothing else did.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import INVALID_SAVED_TOKEN_SENTINEL, GitHubCredentialStore  # noqa: E402

USERNAME = "alice"


@pytest.fixture
def store(monkeypatch):
    """A store with its database lookup stubbed out, so these cover the store alone.

    The stub is what makes that true: without it a case that does not seed the
    cache falls through to a real ``SessionLocal()`` against whatever database
    the run happens to point at, and reads as a store bug.
    """
    monkeypatch.setattr("auth._load_saved_personal_access_token", lambda _username: None)
    return GitHubCredentialStore()


def _with_saved(store, token):
    store._pat_cache[USERNAME] = (token, float("inf"))
    return store


class TestTheSentinelIsNotHandedOut:
    def test_get_reports_no_credential(self, store):
        _with_saved(store, INVALID_SAVED_TOKEN_SENTINEL)
        assert store.get(USERNAME) is None

    def test_subscript_raises_rather_than_returning_it(self, store):
        _with_saved(store, INVALID_SAVED_TOKEN_SENTINEL)
        with pytest.raises(KeyError):
            store[USERNAME]

    def test_membership_agrees_with_lookup(self, store):
        """`in` and `[]` disagreeing is how a caller ends up with the sentinel
        after guarding correctly."""
        _with_saved(store, INVALID_SAVED_TOKEN_SENTINEL)
        assert USERNAME not in store

    def test_a_real_saved_token_is_unaffected(self, store):
        _with_saved(store, "ghp_a_real_saved_token")
        assert store.get(USERNAME) == "ghp_a_real_saved_token"
        assert USERNAME in store


class TestItDoesNotShadowAWorkingSessionToken:
    """The store prefers a saved PAT over the in-memory OAuth token, so an
    unreadable PAT took precedence over a credential that worked."""

    def test_the_oauth_token_is_used_instead(self, store):
        _with_saved(store, INVALID_SAVED_TOKEN_SENTINEL)
        store[USERNAME] = "gho_live_session_token"
        assert store.get(USERNAME) == "gho_live_session_token"

    def test_a_readable_pat_still_wins_over_the_oauth_token(self, store):
        """The preference itself is deliberate and must survive the fix."""
        _with_saved(store, "ghp_a_real_saved_token")
        store[USERNAME] = "gho_live_session_token"
        assert store.get(USERNAME) == "ghp_a_real_saved_token"


class TestCallersCanTellTheTwoApartToSayWhy:
    def test_an_unreadable_token_is_reported_as_such(self, store):
        _with_saved(store, INVALID_SAVED_TOKEN_SENTINEL)
        assert store.has_unreadable_saved_token(USERNAME) is True

    def test_a_readable_token_is_not(self, store):
        _with_saved(store, "ghp_a_real_saved_token")
        assert store.has_unreadable_saved_token(USERNAME) is False

    def test_no_saved_token_at_all_is_not(self, store):
        _with_saved(store, None)
        assert store.has_unreadable_saved_token(USERNAME) is False
