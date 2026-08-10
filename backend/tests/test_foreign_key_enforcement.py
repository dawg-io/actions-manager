"""
Tests that SQLite foreign key enforcement is actually on (issue #1811).

SQLite defaults `PRAGMA foreign_keys` to OFF, which made all 36 ON DELETE
CASCADE declarations in models.py silent no-ops: deleting a parent left its
children behind as orphans, with no error. database.py now registers a
connect-time listener on the Engine class so every connection enables it.

These assert the behaviour that silently did not work, so a regression is
loud rather than invisible.
"""
import sys
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Importing database registers the Engine-level listener for this process.
import database  # noqa: F401
from database import Base, _sqlite_enable_foreign_keys
from models import (
    Account,
    Project,
    ProjectMembership,
    ProjectDisplayOrder,
    Repo,
    WorkspaceMember,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _account(db, github_user="fkuser"):
    account = Account(github_user=github_user, github_email=f"{github_user}@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    db.add(WorkspaceMember(user_id=account.user_id, workspace_role="admin"))
    db.commit()
    return account


def _project(db, account, name="fkproject", code="FKP"):
    project = Project(project_name=name, project_code=code, user_id=account.user_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestPragmaIsEnabled:
    def test_foreign_keys_pragma_is_on_for_a_new_engine(self):
        # Any engine in the process, not just database.engine — the listener is
        # registered on the Engine class precisely so this holds everywhere.
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    def test_listener_ignores_non_sqlite_connections(self):
        # PostgreSQL enforces natively; the guard must leave its driver alone.
        class NotSqlite:
            def __init__(self):
                self.executed = []

            def execute(self, sql):
                self.executed.append(sql)

        conn = NotSqlite()
        _sqlite_enable_foreign_keys(conn, None)
        assert conn.executed == []


class TestCascadeActuallyFires:
    def test_deleting_a_project_removes_its_children(self, db_session):
        account = _account(db_session)
        project = _project(db_session, account)
        db_session.add_all([
            ProjectMembership(
                user_id=account.user_id, project_id=project.project_id, project_role="project_viewer"
            ),
            ProjectDisplayOrder(user_id=account.user_id, project_id=project.project_id, position=0),
        ])
        db_session.commit()

        db_session.delete(project)
        db_session.commit()

        # Before #1811 both of these survived as orphans.
        assert db_session.query(ProjectMembership).count() == 0
        assert db_session.query(ProjectDisplayOrder).count() == 0

    def test_other_projects_children_are_untouched(self, db_session):
        account = _account(db_session)
        doomed = _project(db_session, account, name="doomed", code="DOOM")
        kept = _project(db_session, account, name="kept", code="KEPT")
        db_session.add_all([
            ProjectDisplayOrder(user_id=account.user_id, project_id=doomed.project_id, position=0),
            ProjectDisplayOrder(user_id=account.user_id, project_id=kept.project_id, position=1),
        ])
        db_session.commit()

        db_session.delete(doomed)
        db_session.commit()

        remaining = db_session.query(ProjectDisplayOrder).all()
        assert [r.project_id for r in remaining] == [kept.project_id]


class TestReferentialIntegrity:
    def test_inserting_a_child_with_a_missing_parent_is_rejected(self, db_session):
        account = _account(db_session)
        db_session.add(ProjectDisplayOrder(user_id=account.user_id, project_id=999999, position=0))

        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_set_null_foreign_key_nulls_instead_of_failing(self, db_session):
        # projects.validation_repo_id is ON DELETE SET NULL on a nullable column,
        # so removing the repo must clear the pointer rather than raise.
        account = _account(db_session)
        repo = Repo(repo_name="acme/validation")
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        project = _project(db_session, account)
        project.validation_repo_id = repo.repo_id
        db_session.commit()

        db_session.delete(repo)
        db_session.commit()
        db_session.refresh(project)

        assert project.validation_repo_id is None
        assert db_session.query(Project).count() == 1
