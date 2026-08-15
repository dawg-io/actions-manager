"""
Tests for the drift settings API.

Drift cadence used to be an env var, so the only way to change it was shell
access. Now it is a workspace setting, which means the app itself has to
enforce what the container used to: only admins may change it, and the values
they can save have to stay inside sane bounds — a 1-second poll or a 500-project
batch would burn the install's GitHub rate limit.

Reads are deliberately open to any member: the per-project drift control needs
the global default to label its "inherit" option.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import Base, get_db
from models import Account, DriftSettings, WorkspaceMember
from authorization import _get_db as auth_get_db
from auth import user_tokens, create_auth_session

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SETTINGS_URL = "/api/drift/settings"

VALID_PAYLOAD = {
    "sweep_enabled": True,
    "recheck_interval_minutes": 30,
    "batch_size": 3,
    "poll_interval_seconds": 120,
}


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_get_db] = override_get_db
    original_factory = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    Base.metadata.create_all(bind=engine)
    yield
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                db.execute(table.delete())
            except Exception:
                pass
        db.commit()
    finally:
        db.close()
    app.state.middleware_db_factory = original_factory
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(auth_get_db, None)
    user_tokens.clear()
    user_tokens._pat_cache.clear()


@pytest.fixture
def test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user(test_db, name, role):
    user = Account(github_user=name, github_email=f"{name}@example.com",
                   account_type="enterprise", github_account_type="User")
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    test_db.add(WorkspaceMember(user_id=user.user_id, workspace_role=role))
    test_db.commit()
    user.session_token = create_auth_session(name, test_db)
    return user


@pytest.fixture
def admin_user(test_db):
    return _user(test_db, "admin-user", "admin")


@pytest.fixture
def member_user(test_db):
    return _user(test_db, "member-user", "member")


def _auth(user):
    return {"Authorization": "Bearer " + user.session_token}


client = TestClient(app)


class TestReadingSettings:
    def test_defaults_are_returned_when_nothing_is_saved(self, member_user):
        """Every install starts with no row. It must read as the old env-var
        defaults rather than zeros or an error."""
        resp = client.get(SETTINGS_URL, headers=_auth(member_user))

        assert resp.status_code == 200
        assert resp.json() == {
            "sweep_enabled": True,
            "recheck_interval_minutes": 15,
            "batch_size": 5,
            "poll_interval_seconds": 60,
        }

    def test_a_non_admin_member_can_read(self, member_user):
        """The per-project control needs the default to label 'inherit'."""
        assert client.get(SETTINGS_URL, headers=_auth(member_user)).status_code == 200

    def test_unauthenticated_is_rejected(self):
        assert client.get(SETTINGS_URL).status_code == 401


class TestWritingSettings:
    def test_an_admin_can_save(self, admin_user, test_db):
        resp = client.put(SETTINGS_URL, json=VALID_PAYLOAD, headers=_auth(admin_user))

        assert resp.status_code == 200
        assert resp.json()["recheck_interval_minutes"] == 30
        assert test_db.query(DriftSettings).first().recheck_interval_minutes == 30

    def test_the_saved_value_is_what_is_read_back(self, admin_user, member_user):
        client.put(SETTINGS_URL, json=VALID_PAYLOAD, headers=_auth(admin_user))

        assert client.get(SETTINGS_URL, headers=_auth(member_user)).json() == VALID_PAYLOAD

    def test_saving_twice_updates_the_same_row(self, admin_user, test_db):
        """Single-row table — a second save must not stack up rows the worker
        would then read non-deterministically."""
        client.put(SETTINGS_URL, json=VALID_PAYLOAD, headers=_auth(admin_user))
        client.put(SETTINGS_URL, json={**VALID_PAYLOAD, "batch_size": 7},
                   headers=_auth(admin_user))

        rows = test_db.query(DriftSettings).all()
        assert len(rows) == 1
        assert rows[0].batch_size == 7

    def test_the_kill_switch_persists(self, admin_user, member_user):
        client.put(SETTINGS_URL, json={**VALID_PAYLOAD, "sweep_enabled": False},
                   headers=_auth(admin_user))

        assert client.get(SETTINGS_URL, headers=_auth(member_user)).json()["sweep_enabled"] is False

    def test_a_non_admin_cannot_save(self, member_user, test_db):
        resp = client.put(SETTINGS_URL, json=VALID_PAYLOAD, headers=_auth(member_user))

        assert resp.status_code == 403
        assert test_db.query(DriftSettings).first() is None

    def test_unauthenticated_cannot_save(self):
        assert client.put(SETTINGS_URL, json=VALID_PAYLOAD).status_code == 401


class TestValidationBounds:
    """Bad values here are a rate-limit problem, not a cosmetic one."""

    @pytest.mark.parametrize("field,value", [
        ("recheck_interval_minutes", 0),
        ("recheck_interval_minutes", -5),
        ("batch_size", 0),
        ("batch_size", 500),
        ("poll_interval_seconds", 1),
        ("poll_interval_seconds", 0),
    ])
    def test_out_of_range_values_are_rejected(self, admin_user, test_db, field, value):
        resp = client.put(SETTINGS_URL, json={**VALID_PAYLOAD, field: value},
                          headers=_auth(admin_user))

        assert resp.status_code == 422
        assert test_db.query(DriftSettings).first() is None
