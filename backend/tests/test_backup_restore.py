"""
Whole-installation backup and restore (issue #1878).

Covers the engine (round-trip, integrity, compatibility, credential safety) and
the admin-only download endpoint. The first-boot restore surface is tested
through workspace_is_uninitialized, which is the gate it hangs off.
"""

import backup_engine
import hashlib
import io
import json
import os
import sys
import tarfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from authorization import get_current_user
from sqlalchemy import BigInteger, Integer
from backup_engine import (
    BACKUP_FORMAT_VERSION,
    BackupError,
    create_backup,
    restore_backup,
    validate_backup,
    workspace_is_uninitialized,
)
from database import get_db
from main import app
from models import (
    Base,
    Account,
    AuthSession,
    Project,
    SEED_ACCOUNT_GITHUB_USER,
    Workflow,
    WorkspaceMember,
)

client = TestClient(app)

PAT_CIPHERTEXT = "gAAAAABm-not-a-real-token-just-ciphertext"


@pytest.fixture()
def db_session():
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
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _add_account(db, github_user="alice", role="admin", pat=PAT_CIPHERTEXT):
    account = Account(
        github_user=github_user,
        github_email=f"{github_user}@example.com",
        account_type="free",
        github_pat_token_encrypted=pat,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    if role:
        db.add(WorkspaceMember(user_id=account.user_id, workspace_role=role))
        db.commit()
    return account


def _seed_install(db):
    """A small but representative installation: an account, a role, a project,
    a workflow, and a live session that must not survive a backup."""
    account = _add_account(db)
    db.add(Project(project_name="Demo", project_code="DEMO", user_id=account.user_id))
    db.add(Workflow(workflow_name="ci", workflow_yaml="on: push"))
    db.add(AuthSession(
        token_hash="deadbeef",
        github_user=account.github_user,
        expires_at=datetime(2099, 1, 1),
    ))
    db.commit()
    return account


def _rewrite_archive(source, destination, transform):
    """Copy an archive, passing each member through `transform(name, bytes)`."""
    with tarfile.open(source, "r:gz") as src, tarfile.open(destination, "w:gz") as dst:
        for member in src.getmembers():
            payload = transform(member.name, src.extractfile(member).read())
            member.size = len(payload)
            dst.addfile(member, io.BytesIO(payload))
    return destination


class TestRoundTrip:
    def test_backup_then_restore_reproduces_every_row(self, db_session, tmp_path):
        _seed_install(db_session)
        archive = create_backup(db_session, tmp_path / "b.tar.gz")

        for table in reversed(Base.metadata.sorted_tables):
            db_session.execute(table.delete())
        db_session.commit()
        assert db_session.query(Account).count() == 0

        result = restore_backup(db_session, tmp_path / "b.tar.gz", run_migrations=False)

        assert db_session.query(Account).one().github_user == "alice"
        assert db_session.query(Project).one().project_name == "Demo"
        assert db_session.query(Workflow).one().workflow_name == "ci"
        assert result["total_rows"] == 4
        assert archive["tables"]["accounts"]["rows"] == 1

    def test_datetimes_survive_the_round_trip(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")
        before = db_session.query(Project).one().created_at

        for table in reversed(Base.metadata.sorted_tables):
            db_session.execute(table.delete())
        db_session.commit()
        restore_backup(db_session, tmp_path / "b.tar.gz", run_migrations=False)

        assert db_session.query(Project).one().created_at == before


class TestCredentialSafety:
    def test_pat_is_carried_as_ciphertext_and_still_decryptable_after_restore(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        raw = (tmp_path / "b.tar.gz").read_bytes()
        with tarfile.open(tmp_path / "b.tar.gz", "r:gz") as archive:
            accounts = archive.extractfile("tables/accounts.jsonl").read().decode()
        assert PAT_CIPHERTEXT in accounts, "the encrypted column must be carried across"
        assert b"decrypt" not in raw.lower()

        for table in reversed(Base.metadata.sorted_tables):
            db_session.execute(table.delete())
        db_session.commit()
        restore_backup(db_session, tmp_path / "b.tar.gz", run_migrations=False)

        # Unchanged ciphertext is what makes it decryptable again under the same key.
        assert db_session.query(Account).one().github_pat_token_encrypted == PAT_CIPHERTEXT

    def test_secret_key_never_appears_in_the_archive(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "super-secret-value")
        _seed_install(db_session)
        manifest = create_backup(db_session, tmp_path / "b.tar.gz")

        assert b"super-secret-value" not in (tmp_path / "b.tar.gz").read_bytes()
        assert manifest["secret_key_fingerprint"]
        assert "super-secret-value" not in manifest["secret_key_fingerprint"]

    def test_live_sessions_are_not_backed_up(self, db_session, tmp_path):
        _seed_install(db_session)
        assert db_session.query(AuthSession).count() == 1

        manifest = create_backup(db_session, tmp_path / "b.tar.gz")
        assert "auth_sessions" not in manifest["tables"]

        with tarfile.open(tmp_path / "b.tar.gz", "r:gz") as archive:
            assert "tables/auth_sessions.jsonl" not in archive.getnames()
            assert b"deadbeef" not in archive.extractfile("manifest.json").read()

    def test_restore_clears_sessions_that_were_live_on_the_target(self, db_session, tmp_path):
        """Sessions are neither carried nor left behind.

        Leaving the target's sessions in place would be worse than carrying
        them: auth_sessions keys on a username, so a session that survived
        would authenticate against whatever account the restore installed
        under that name.
        """
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        db_session.add(AuthSession(
            token_hash="session-live-on-the-target",
            github_user="alice",
            expires_at=datetime(2099, 1, 1),
        ))
        db_session.commit()
        assert db_session.query(AuthSession).count() == 2

        restore_backup(db_session, tmp_path / "b.tar.gz", force=True, run_migrations=False)

        assert db_session.query(AuthSession).count() == 0

    def test_a_different_secret_key_warns_rather_than_silently_breaking_pats(
        self, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SECRET_KEY", "original-key")
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        monkeypatch.setenv("SECRET_KEY", "a-completely-different-key")
        report = validate_backup(tmp_path / "b.tar.gz", db_session)

        assert report["ok"], "a key mismatch must not block an otherwise valid restore"
        assert any("SECRET_KEY differs" in w for w in report["warnings"])


class TestIntegrity:
    def test_edited_table_data_fails_its_checksum(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        tampered = _rewrite_archive(
            tmp_path / "b.tar.gz",
            tmp_path / "tampered.tar.gz",
            lambda name, data: data.replace(b"alice", b"mallory")
            if name.endswith("accounts.jsonl")
            else data,
        )

        report = validate_backup(tampered, db_session)
        assert not report["ok"]
        assert any("checksum" in e for e in report["errors"])

    @pytest.mark.parametrize(
        "name,payload",
        [
            ("truncated.tar.gz", None),
            ("junk.tar.gz", b"this is not an archive at all"),
            ("empty.tar.gz", b""),
        ],
    )
    def test_unreadable_archives_are_rejected_cleanly(self, db_session, tmp_path, name, payload):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        # A truncated upload raises EOFError rather than OSError; it must still
        # surface as a BackupError, not an unhandled crash.
        content = (tmp_path / "b.tar.gz").read_bytes()[:200] if payload is None else payload
        (tmp_path / name).write_bytes(content)

        with pytest.raises(BackupError):
            validate_backup(tmp_path / name, db_session)

    def test_archive_without_a_manifest_is_rejected(self, db_session, tmp_path):
        path = tmp_path / "nomanifest.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            info = tarfile.TarInfo(name="tables/accounts.jsonl")
            info.size = 0
            archive.addfile(info, io.BytesIO(b""))

        with pytest.raises(BackupError, match="no manifest"):
            validate_backup(path, db_session)

    def test_restore_refuses_an_invalid_archive(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")
        tampered = _rewrite_archive(
            tmp_path / "b.tar.gz",
            tmp_path / "tampered.tar.gz",
            lambda name, data: data.replace(b"alice", b"mallory")
            if name.endswith("accounts.jsonl")
            else data,
        )

        with pytest.raises(BackupError):
            restore_backup(db_session, tampered, force=True, run_migrations=False)
        # The rejected restore must not have emptied the installation first.
        assert db_session.query(Account).count() == 1


class TestCompatibility:
    def test_backup_from_a_newer_schema_is_refused(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        def add_future_migration(name, data):
            if name != "manifest.json":
                return data
            manifest = json.loads(data)
            manifest["migrations"].append("migrate_from_the_future.py")
            return json.dumps(manifest).encode()

        newer = _rewrite_archive(tmp_path / "b.tar.gz", tmp_path / "newer.tar.gz", add_future_migration)
        report = validate_backup(newer, db_session)

        assert not report["ok"]
        assert any("newer schema" in e for e in report["errors"])

    def test_backup_in_a_newer_format_is_refused(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        def bump_format(name, data):
            if name != "manifest.json":
                return data
            manifest = json.loads(data)
            manifest["backup_format_version"] = "99.0"
            return json.dumps(manifest).encode()

        newer = _rewrite_archive(tmp_path / "b.tar.gz", tmp_path / "fmt.tar.gz", bump_format)
        report = validate_backup(newer, db_session)

        assert not report["ok"]
        assert any("newer than this installation supports" in e for e in report["errors"])

    def test_backup_predating_a_migration_restores_and_flags_the_gap(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        def drop_last_migration(name, data):
            if name != "manifest.json":
                return data
            manifest = json.loads(data)
            manifest["migrations"] = manifest["migrations"][:-1]
            return json.dumps(manifest).encode()

        older = _rewrite_archive(tmp_path / "b.tar.gz", tmp_path / "older.tar.gz", drop_last_migration)
        report = validate_backup(older, db_session)

        assert report["ok"]
        assert any("predates" in w for w in report["warnings"])

    def test_manifest_referencing_a_missing_member_is_rejected(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        def claim_a_member_that_is_not_there(name, data):
            if name != "manifest.json":
                return data
            manifest = json.loads(data)
            manifest["tables"]["table_from_a_later_release"] = {
                "rows": 0,
                "sha256": hashlib.sha256(b"").hexdigest(),
                "member": "tables/table_from_a_later_release.jsonl",
            }
            return json.dumps(manifest).encode()

        path = _rewrite_archive(
            tmp_path / "b.tar.gz", tmp_path / "unknown.tar.gz", claim_a_member_that_is_not_there
        )
        report = validate_backup(path, db_session)

        assert not report["ok"]
        assert any("missing from the archive" in e for e in report["errors"])

    def test_tables_this_release_does_not_have_are_reported_and_skipped(self, db_session, tmp_path):
        """A backup from a later release carries tables this one lacks. Those are
        skipped with a warning rather than failing an otherwise valid restore."""
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        extra_member = "tables/table_from_a_later_release.jsonl"
        path = tmp_path / "extra.tar.gz"
        with tarfile.open(tmp_path / "b.tar.gz", "r:gz") as src, tarfile.open(path, "w:gz") as dst:
            for member in src.getmembers():
                data = src.extractfile(member).read()
                if member.name == "manifest.json":
                    manifest = json.loads(data)
                    manifest["tables"]["table_from_a_later_release"] = {
                        "rows": 0,
                        "sha256": hashlib.sha256(b"").hexdigest(),
                        "member": extra_member,
                    }
                    data = json.dumps(manifest).encode()
                member.size = len(data)
                dst.addfile(member, io.BytesIO(data))
            info = tarfile.TarInfo(name=extra_member)
            info.size = 0
            dst.addfile(info, io.BytesIO(b""))

        report = validate_backup(path, db_session)
        assert report["ok"]
        assert any("does not have" in w for w in report["warnings"])

        result = restore_backup(db_session, path, force=True, run_migrations=False)
        assert "table_from_a_later_release" in result["skipped_tables"]


class TestUninitializedGate:
    def test_empty_installation_is_uninitialized(self, db_session):
        assert workspace_is_uninitialized(db_session) is True

    def test_seed_account_alone_still_counts_as_uninitialized(self, db_session):
        # The seed account is created by a migration before anyone can log in;
        # counting it would make an untouched install look occupied.
        _add_account(db_session, SEED_ACCOUNT_GITHUB_USER, role="admin")
        assert workspace_is_uninitialized(db_session) is True

    def test_one_real_member_closes_the_window(self, db_session):
        _add_account(db_session, "alice", role="admin")
        assert workspace_is_uninitialized(db_session) is False

    def test_restore_refuses_an_occupied_installation_without_force(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        with pytest.raises(BackupError, match="already has users"):
            restore_backup(db_session, tmp_path / "b.tar.gz", run_migrations=False)

    def test_force_overrides_the_occupied_check(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        result = restore_backup(db_session, tmp_path / "b.tar.gz", force=True, run_migrations=False)
        assert result["total_rows"] == 4


class TestBackupDownloadEndpoint:
    def _authenticate_as(self, db, role):
        account = _add_account(db, f"{role}-user", role=role)
        app.dependency_overrides[get_current_user] = lambda: account
        return account

    @pytest.mark.parametrize("role", ["read_only", "member"])
    def test_non_admins_cannot_download_a_backup(self, db_session, role):
        self._authenticate_as(db_session, role)
        assert client.get("/api/workspace/backup").status_code == 403
        assert client.get("/api/workspace/backup/info").status_code == 403

    def test_admin_downloads_a_usable_archive(self, db_session):
        self._authenticate_as(db_session, "admin")
        response = client.get("/api/workspace/backup")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gzip"
        assert "actionsmanager-backup-" in response.headers["content-disposition"]

        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
            manifest = json.loads(archive.extractfile("manifest.json").read())
        assert manifest["backup_format_version"] == BACKUP_FORMAT_VERSION
        assert "auth_sessions" not in manifest["tables"]

    def test_admin_sees_row_counts_before_downloading(self, db_session):
        self._authenticate_as(db_session, "admin")
        db_session.add(Project(project_name="Demo", project_code="DEMO", user_id=1))
        db_session.commit()

        body = client.get("/api/workspace/backup/info").json()
        assert body["tables"]["projects"] == 1
        assert body["total_rows"] >= 1
        assert "auth_sessions" in body["excluded_tables"]


class TestDownloadFilenameIsReadableCrossOrigin:
    """A split-origin deployment must be able to read the download filename.

    Content-Disposition is not CORS-safelisted. Without it in expose_headers the
    browser receives the header but JS cannot read it, so every backup saves
    under a generic name — and for backups the timestamp is how an operator
    tells one archive from another. Caught by the e2e download test; guarded
    here because that test mocks the server.
    """

    def test_content_disposition_is_exposed_to_cross_origin_callers(self, db_session):
        account = _add_account(db_session, "admin-user", role="admin")
        app.dependency_overrides[get_current_user] = lambda: account

        response = client.get("/api/workspace/backup", headers={"Origin": "http://localhost:3000"})

        assert response.status_code == 200
        exposed = response.headers.get("access-control-expose-headers", "")
        assert "Content-Disposition" in exposed


class TestIdentitySequences:
    """A restore writes primary keys explicitly, which does not advance the
    sequences behind them on PostgreSQL.

    This is the one defect the rest of this file structurally cannot catch:
    SQLite derives the next rowid from the table's contents, so the collision
    only exists on PostgreSQL. The first test below therefore drives the logic
    directly with a recording session; the second runs the real thing, and is
    skipped unless a PostgreSQL DATABASE_URL is supplied.
    """

    def test_every_integer_primary_key_gets_its_sequence_reset(self):
        issued = []

        class FakeDialect:
            name = "postgresql"

        class FakeBind:
            dialect = FakeDialect()

        class RecordingSession:
            def get_bind(self):
                return FakeBind()

            def execute(self, statement):
                sql = str(statement)
                params = getattr(statement, "_bindparams", {})
                issued.append((sql, {k: v.value for k, v in params.items()}))
                return self

            def scalar(self):
                # Stand in for pg_get_serial_sequence, then for MAX(col).
                return "some_table_id_seq" if "pg_get_serial_sequence" in issued[-1][0] else 41

            def commit(self):
                pass

        backup_engine._resync_sequences(RecordingSession(), lambda _msg: None)

        setvals = [(sql, params) for sql, params in issued if "setval" in sql]
        assert setvals, "no sequence was reset"
        # One per integer primary key across every backed-up table.
        assert len(setvals) == sum(
            1
            for table in backup_engine.backup_tables()
            for column in table.primary_key.columns
            if isinstance(column.type, (Integer, BigInteger))
        )
        # MAX + 1, with is_called false, so the next insert takes exactly MAX+1.
        assert all(params["next_value"] == 42 for _sql, params in setvals)

    def test_sqlite_needs_no_resync(self, db_session, tmp_path):
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        # No error, and nothing issued — SQLite has no sequences to move.
        restore_backup(db_session, tmp_path / "b.tar.gz", force=True, run_migrations=False)

        assert db_session.query(Account).count() == 1

    @pytest.mark.skipif(
        "postgres" not in os.getenv("BACKUP_TEST_DATABASE_URL", ""),
        reason="needs BACKUP_TEST_DATABASE_URL pointing at PostgreSQL",
    )
    def test_postgresql_can_insert_after_a_restore(self, tmp_path):
        """The real reproduction: restore into a fresh database, then insert.

        Without the resync this raises
        'duplicate key value violates unique constraint "accounts_pkey"'.
        """
        from sqlalchemy import create_engine as _create_engine

        engine = _create_engine(os.environ["BACKUP_TEST_DATABASE_URL"])
        Session = sessionmaker(bind=engine)

        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        db = Session()
        for index in range(5):
            db.add(Account(github_user=f"user{index}", github_email=f"u{index}@e.com", account_type="free"))
        db.commit()
        create_backup(db, tmp_path / "b.tar.gz")
        db.close()

        # A genuinely fresh target, as a new container would be.
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        db = Session()
        try:
            restore_backup(db, tmp_path / "b.tar.gz", force=True, run_migrations=False)

            db.add(Account(github_user="newcomer", github_email="n@e.com", account_type="free"))
            db.commit()

            assert db.query(Account).count() == 6
        finally:
            db.close()
            Base.metadata.drop_all(engine)


class TestVersionOrdering:
    def test_versions_compare_numerically_not_lexicographically(self):
        # As strings "2.0" > "10.0", which would refuse a genuinely older backup
        # as "newer" — during a recovery, the worst moment to be wrong.
        assert backup_engine._version_tuple("2.0") < backup_engine._version_tuple("10.0")
        assert backup_engine._version_tuple("1.10") > backup_engine._version_tuple("1.9")
        assert backup_engine._version_tuple("nonsense") == (0,)


class TestResyncFailureIsNotFatal:
    def test_a_sequence_failure_warns_instead_of_reporting_the_restore_failed(
        self, db_session, tmp_path, monkeypatch
    ):
        """The rows are committed by the time sequences are reset.

        Raising here would report failure for a restore that succeeded — and
        because the data landed, the installation no longer looks uninitialized,
        so the operator could neither retry through the UI nor understand why.
        """
        _seed_install(db_session)
        create_backup(db_session, tmp_path / "b.tar.gz")

        def explode(_db, _say):
            raise RuntimeError("permission denied for sequence accounts_user_id_seq")

        monkeypatch.setattr(backup_engine, "_resync_sequences", explode)

        result = restore_backup(db_session, tmp_path / "b.tar.gz", force=True, run_migrations=False)

        # The data is there ...
        assert db_session.query(Account).one().github_user == "alice"
        # ... and the operator is told what still needs doing.
        assert any("identity sequences" in w for w in result["warnings"])
        assert any("backup_cli.py restore" in w for w in result["warnings"])


class TestDecompressionLimits:
    """A crafted high-ratio archive must be refused rather than exhausting memory.

    The first-boot restore endpoint is reachable before any account exists, so
    this is unauthenticated input. The compressed side is already capped when the
    upload is staged; these cover the decompressed side.
    """

    def _bomb(self, path, member, size):
        with tarfile.open(path, "w:gz") as archive:
            payload = b"\0" * size
            info = tarfile.TarInfo(member)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    def test_an_oversized_manifest_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_engine, "MAX_MANIFEST_BYTES", 1024)
        archive = tmp_path / "bomb.tar.gz"
        self._bomb(archive, backup_engine.MANIFEST_NAME, 512 * 1024)

        with pytest.raises(BackupError, match="crafted to exhaust memory"):
            backup_engine.read_manifest(archive)

    def test_an_oversized_table_member_fails_validation_rather_than_allocating(
        self, db_session, tmp_path, monkeypatch
    ):
        _seed_install(db_session)
        archive = tmp_path / "b.tar.gz"
        create_backup(db_session, archive)

        monkeypatch.setattr(backup_engine, "MAX_MEMBER_BYTES", 8)
        report = validate_backup(archive, db_session)

        assert not report["ok"]
        assert any("exhaust memory" in e for e in report["errors"])
