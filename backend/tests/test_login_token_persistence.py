"""
Tests that a logged-in account ends up with a durably stored GitHub token.

github_callback persists the login token, but only for logins that happen after
that behaviour shipped. A session created before it — or simply before this
process started — leaves the account authenticated with an in-memory-only
credential and nothing in the database.

The drift sweep runs with no request context and reads only the stored token, so
those owners' projects report "no saved GitHub token" after every restart while
they are logged in and Check Now works. resolve_authenticated_user now persists
the in-memory token on the first authenticated request, closing that window.
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402
from auth import create_auth_session, resolve_authenticated_user, user_tokens  # noqa: E402
from database import Base  # noqa: E402
from models import Account  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

USERNAME = "alice"


@pytest.fixture(autouse=True)
def _clean_store():
    Base.metadata.create_all(bind=engine)
    user_tokens.clear()
    user_tokens._pat_cache.clear()
    yield
    user_tokens.clear()
    user_tokens._pat_cache.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _account(db) -> Account:
    user = Account(github_user=USERNAME, github_email="a@example.com", account_type="free")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _request(session_token: str) -> Request:
    """Minimal ASGI scope carrying the bearer session token the resolver reads."""
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {session_token}".encode())],
        "state": {},
    }
    return Request(scope)


def _resolve(db, session_token):
    with patch.object(auth, "SECRET_KEY", "unit-test-secret"):
        return resolve_authenticated_user(_request(session_token), db)


class TestLoginTokenPersistence:
    def test_an_in_memory_only_token_is_persisted_on_first_request(self, db):
        """The regression: without this, a restart strands the sweep with no
        credential even though the owner is signed in."""
        user = _account(db)
        token = create_auth_session(USERNAME, db)
        user_tokens[USERNAME] = "gho_live_login_token"
        assert user.github_pat_token_encrypted is None

        _resolve(db, token)

        db.refresh(user)
        assert user.github_pat_token_encrypted is not None
        assert user.github_pat_updated_at is not None

    def test_the_persisted_token_is_the_one_the_sweep_reads_back(self, db):
        """Stored encrypted, and must decrypt to the original — the sweep
        resolves credentials through the same store."""
        _account(db)
        token = create_auth_session(USERNAME, db)
        user_tokens[USERNAME] = "gho_live_login_token"

        _resolve(db, token)

        with patch.object(auth, "SECRET_KEY", "unit-test-secret"), \
             patch.object(auth, "SessionLocal", TestingSessionLocal):
            user_tokens.invalidate_pat(USERNAME)
            assert auth._load_saved_personal_access_token(USERNAME) == "gho_live_login_token"

    def test_an_existing_saved_token_is_never_overwritten(self, db):
        """A deliberately saved PAT outranks a login token and must survive."""
        user = _account(db)
        with patch.object(auth, "SECRET_KEY", "unit-test-secret"):
            user.github_pat_token_encrypted = auth._encrypt_saved_token("ghp_deliberate_pat")
        db.commit()
        before = user.github_pat_token_encrypted
        token = create_auth_session(USERNAME, db)
        user_tokens[USERNAME] = "gho_live_login_token"

        _resolve(db, token)

        db.refresh(user)
        assert user.github_pat_token_encrypted == before

    def test_no_in_memory_token_leaves_the_account_untouched(self, db):
        """Nothing to recover — this account genuinely has to sign in again, and
        the resolver must not invent a credential or fail the request."""
        user = _account(db)
        token = create_auth_session(USERNAME, db)

        resolved = _resolve(db, token)

        assert resolved.github_user == USERNAME
        db.refresh(user)
        assert user.github_pat_token_encrypted is None

    def test_a_removed_token_is_not_quietly_restored(self, db):
        """Removing a token must actually remove it. The in-memory login token
        outlives the delete, so without clearing it the next request re-saves
        the credential the user explicitly deleted."""
        user = _account(db)
        token = create_auth_session(USERNAME, db)
        user_tokens[USERNAME] = "gho_live_login_token"
        _resolve(db, token)
        db.refresh(user)
        assert user.github_pat_token_encrypted is not None  # persisted

        # What DELETE /api/user/{username}/github-token does.
        user.github_pat_token_encrypted = None
        db.commit()
        user_tokens.invalidate_pat(USERNAME)
        user_tokens.pop(USERNAME, None)

        _resolve(db, token)

        db.refresh(user)
        assert user.github_pat_token_encrypted is None

    def test_a_database_error_while_persisting_does_not_fail_the_request(self, db):
        """This runs on the auth path of every request; a locked database must
        not turn an ordinary authenticated call into a 500."""
        _account(db)
        token = create_auth_session(USERNAME, db)
        user_tokens[USERNAME] = "gho_live_login_token"

        with patch.object(auth, "SECRET_KEY", "unit-test-secret"), \
             patch.object(db, "commit", side_effect=OperationalError("locked", {}, Exception())):
            resolved = resolve_authenticated_user(_request(token), db)

        assert resolved.github_user == USERNAME

    def test_a_missing_secret_key_does_not_break_authentication(self, db):
        """Persisting is best-effort: login must keep working without a
        SECRET_KEY, exactly as github_callback already tolerates."""
        user = _account(db)
        token = create_auth_session(USERNAME, db)
        user_tokens[USERNAME] = "gho_live_login_token"

        with patch.object(auth, "_encrypt_saved_token",
                          side_effect=HTTPException(status_code=503, detail="no key")):
            resolved = resolve_authenticated_user(_request(token), db)

        assert resolved.github_user == USERNAME
        db.refresh(user)
        assert user.github_pat_token_encrypted is None
