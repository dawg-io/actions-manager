"""
First-boot restore endpoints (issue #1878).

The security argument for these being unauthenticated is that their window is
the same window in which the next person to sign in becomes workspace admin.
These tests pin both halves of that: the window is open when it should be, and
it closes permanently the moment a real member exists.
"""

import io
import os
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backup_engine
import setup_restore
from backup_engine import create_backup
from database import get_db
from main import app
from models import (
    Base,
    Account,
    AuthSession,
    Project,
    SEED_ACCOUNT_GITHUB_USER,
    WorkspaceMember,
)

client = TestClient(app)


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Stage uploads under the test's tmp dir, never /app/data.
    monkeypatch.setattr(setup_restore, "SELF_HOSTED_DATA_DIR", tmp_path)
    # The real runner spawns run_migrations.py, which resolves DATABASE_URL on
    # its own and would migrate the developer's local test.db rather than this
    # in-memory one. The runner has its own coverage; what matters here is that
    # the endpoint reports the outcome.
    monkeypatch.setattr(backup_engine, "_run_migrations", lambda say: True)
    # The write-protection middleware counts members through its own session
    # factory; point it at the same in-memory database.
    monkeypatch.setattr(app.state, "middleware_db_factory", TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)


def _add_account(db, github_user, role="admin"):
    account = Account(
        github_user=github_user,
        github_email=f"{github_user}@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    if role:
        db.add(WorkspaceMember(user_id=account.user_id, workspace_role=role))
        db.commit()
    return account


def _archive_bytes(db, tmp_path):
    """A backup of the current database, as an uploadable file."""
    create_backup(db, tmp_path / "source.tar.gz")
    return (tmp_path / "source.tar.gz").read_bytes()


def _upload(payload: bytes, name="backup.tar.gz"):
    return client.post(
        "/api/setup/restore/validate",
        files={"file": (name, io.BytesIO(payload), "application/gzip")},
    )


class TestSetupStatus:
    def test_empty_installation_reports_uninitialized(self, db_session):
        assert client.get("/api/setup/status").json() == {"uninitialized": True}

    def test_seed_account_alone_still_reports_uninitialized(self, db_session):
        # Created by a migration before anyone can sign in; counting it would
        # make an untouched install look occupied.
        _add_account(db_session, SEED_ACCOUNT_GITHUB_USER, role=None)
        assert client.get("/api/setup/status").json() == {"uninitialized": True}

    def test_one_real_member_reports_initialized(self, db_session):
        _add_account(db_session, "alice", role="admin")
        assert client.get("/api/setup/status").json() == {"uninitialized": False}


class TestValidateUpload:
    def test_reports_what_a_restore_would_do(self, db_session, tmp_path):
        _add_account(db_session, "alice", role="admin")
        db_session.add(Project(project_name="Demo", project_code="DEMO", user_id=1))
        db_session.commit()
        payload = _archive_bytes(db_session, tmp_path)

        for table in reversed(Base.metadata.sorted_tables):
            db_session.execute(table.delete())
        db_session.commit()

        body = _upload(payload).json()

        assert body["ok"] is True
        assert body["total_rows"] == 3
        assert body["tables"]["projects"] == 1
        assert body["upload_token"]
        assert "auth_sessions" not in body["tables"]

    def test_rejects_something_that_is_not_a_backup(self, db_session):
        response = _upload(b"this is not an archive")

        assert response.status_code == 400
        assert "corrupt" in response.json()["detail"].lower()

    def test_rejects_a_truncated_upload(self, db_session, tmp_path):
        payload = _archive_bytes(db_session, tmp_path)

        response = _upload(payload[:200])

        assert response.status_code == 400

    def test_a_rejected_upload_is_not_left_on_disk(self, db_session, tmp_path):
        _upload(b"not an archive")

        staged = list((tmp_path / "restore").glob("*.tar.gz")) if (tmp_path / "restore").is_dir() else []
        assert staged == []

    def test_refuses_once_the_workspace_has_a_member(self, db_session, tmp_path):
        payload = _archive_bytes(db_session, tmp_path)
        _add_account(db_session, "alice", role="admin")

        response = _upload(payload)

        # The write-protection middleware challenges an unauthenticated write
        # before the route's own 409 is reached; either way it does not proceed.
        assert response.status_code in (401, 409)


class TestApplyRestore:
    def _stage(self, db, tmp_path):
        payload = _archive_bytes(db, tmp_path)
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        return _upload(payload).json()["upload_token"]

    def test_applies_a_staged_backup_into_an_empty_installation(self, db_session, tmp_path):
        _add_account(db_session, "alice", role="admin")
        db_session.add(Project(project_name="Demo", project_code="DEMO", user_id=1))
        db_session.commit()
        token = self._stage(db_session, tmp_path)

        response = client.post("/api/setup/restore/apply", data={"upload_token": token})

        assert response.status_code == 200
        assert response.json()["restored_rows"] == 3
        assert response.json()["migrations_ran"] is True
        assert db_session.query(Account).one().github_user == "alice"
        assert db_session.query(Project).one().project_name == "Demo"

    def test_a_restored_workspace_no_longer_offers_restore(self, db_session, tmp_path):
        _add_account(db_session, "alice", role="admin")
        token = self._stage(db_session, tmp_path)

        client.post("/api/setup/restore/apply", data={"upload_token": token})

        assert client.get("/api/setup/status").json() == {"uninitialized": False}

    def test_restoring_does_not_re_promote_the_next_person_to_sign_in(self, db_session, tmp_path):
        """The restored database has members, so first-login-wins must not re-fire
        and hand admin to whoever happens to sign in next."""
        from auth import _ensure_workspace_membership

        _add_account(db_session, "alice", role="admin")
        token = self._stage(db_session, tmp_path)
        client.post("/api/setup/restore/apply", data={"upload_token": token})

        bob = Account(github_user="bob", github_email="bob@example.com", account_type="free")
        db_session.add(bob)
        db_session.commit()
        db_session.refresh(bob)
        _ensure_workspace_membership(bob, db_session)

        membership = db_session.query(WorkspaceMember).filter(WorkspaceMember.user_id == bob.user_id).one()
        assert membership.workspace_role == "read_only"

    def test_the_staged_archive_is_discarded_after_applying(self, db_session, tmp_path):
        _add_account(db_session, "alice", role="admin")
        token = self._stage(db_session, tmp_path)

        client.post("/api/setup/restore/apply", data={"upload_token": token})

        assert list((tmp_path / "restore").glob("*.tar.gz")) == []

    def test_an_unknown_token_is_rejected(self, db_session):
        response = client.post("/api/setup/restore/apply", data={"upload_token": "0" * 32})

        assert response.status_code == 404

    @pytest.mark.parametrize("token", ["../../etc/passwd", "..", "a/b", ".hidden"])
    def test_a_token_pointing_outside_the_staging_directory_is_rejected(self, db_session, token):
        response = client.post("/api/setup/restore/apply", data={"upload_token": token})

        assert response.status_code in (400, 404)
        assert response.status_code != 200

    def test_refuses_once_the_workspace_has_a_member(self, db_session, tmp_path):
        _add_account(db_session, "alice", role="admin")
        token = self._stage(db_session, tmp_path)
        # Someone signs in between staging and confirming.
        _add_account(db_session, "mallory", role="admin")

        response = client.post("/api/setup/restore/apply", data={"upload_token": token})

        assert response.status_code in (401, 409)
        assert db_session.query(Account).filter(Account.github_user == "mallory").count() == 1


class TestStagingHousekeeping:
    def test_abandoned_uploads_are_swept_after_their_ttl(self, db_session, tmp_path, monkeypatch):
        """Nothing else cleans these up: they sit on unauthenticated routes and
        only a restart would otherwise remove them."""
        staging = tmp_path / "restore"
        staging.mkdir(parents=True, exist_ok=True)
        abandoned = staging / "abandoned.tar.gz"
        abandoned.write_bytes(b"stale")
        old = time.time() - setup_restore.STAGED_UPLOAD_TTL_SECONDS - 60
        os.utime(abandoned, (old, old))

        fresh = staging / "fresh.tar.gz"
        fresh.write_bytes(b"recent")

        setup_restore._staging_dir()

        assert not abandoned.exists()
        assert fresh.exists(), "an in-flight upload must survive the sweep"

    def test_staging_falls_back_when_the_data_dir_does_not_exist(self, monkeypatch, tmp_path):
        """/app/data only exists under INSTALLATION_MODE=self-hosted; without a
        fallback, first-boot restore is unusable in development."""
        monkeypatch.setattr(setup_restore, "SELF_HOSTED_DATA_DIR", tmp_path / "definitely-absent")

        root = setup_restore._staging_root()

        assert "definitely-absent" not in str(root)
        assert root.parent == Path(tempfile.gettempdir())


class TestStagingCleanup:
    def test_startup_drops_abandoned_uploads_but_spares_live_ones(self, db_session, tmp_path):
        """Age-based, not a blanket wipe.

        The staging directory is shared, so deleting it wholesale at startup
        would destroy an upload another worker is mid-way through — the operator
        would get an unexplained 404 on a report they are still reading.
        """
        staging = tmp_path / "restore"
        staging.mkdir(parents=True, exist_ok=True)

        abandoned = staging / "abandoned.tar.gz"
        abandoned.write_bytes(b"leftover")
        stale = time.time() - setup_restore.STAGED_UPLOAD_TTL_SECONDS - 60
        os.utime(abandoned, (stale, stale))

        in_flight = staging / "in-flight.tar.gz"
        in_flight.write_bytes(b"someone is using this")

        setup_restore.discard_staged_uploads()

        assert not abandoned.exists()
        assert in_flight.exists()
