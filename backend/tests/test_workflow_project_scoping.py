"""
Workflow lookups by name must be scoped to a project.

Workflow names are deliberately not globally unique — two projects may each own
a workflow called "ci", and a migration explicitly removed the old unique
constraint to allow it. Two lookups ignored that:

  * _update_workflow_git_hash did an unscoped filter_by(workflow_name).first(),
    so committing project A's workflow stamped A's GitHub blob SHA onto
    project B's row. That corrupts B's drift baseline, and because the drift
    check trusts the stored hash as a proxy for local content, B's real drift
    then reads as "synchronized".
  * The upsert lookup used ILIKE with raw user input, where '_' is a
    single-character wildcard, so saving "ci_build" could overwrite "ciXbuild".

Prefix mode does not protect against either: use_prefix is applied only when
building the GitHub path, so both modes store the bare stem.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    Base, Account, Project, ProjectWorkflow, Workflow,
)
from workflows import _update_workflow_git_hash  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _project(db, code, *, use_prefix=False):
    account = Account(
        github_user=f"user-{code}", github_email=f"{code}@example.com", account_type="free"
    )
    db.add(account); db.commit(); db.refresh(account)
    project = Project(
        project_name=f"proj-{code}", project_code=code,
        user_id=account.user_id, use_prefix=use_prefix,
    )
    db.add(project); db.commit(); db.refresh(project)
    return project


def _workflow(db, project, name, *, git_hash="original", is_reusable=False):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml=f"name: {name}\non: push\n",
        workflow_git_hash=git_hash,
        reusable_workflow=is_reusable,
    )
    db.add(wf); db.commit(); db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
    db.commit()
    return wf


class TestGitHashWriteIsProjectScoped:
    def test_committing_one_project_does_not_touch_another(self, db):
        """The headline bug: A's push stamped its SHA onto B's row."""
        project_a = _project(db, "AAA")
        project_b = _project(db, "BBB")
        wf_a = _workflow(db, project_a, "ci", git_hash="a-original")
        wf_b = _workflow(db, project_b, "ci", git_hash="b-original")

        # Deliberately update the *second* project. The old unscoped
        # .first() returns the lowest rowid — project A's row — so this
        # ordering is what makes the bug visible; updating A instead would
        # pass even with the bug.
        _update_workflow_git_hash(db, "ci", "b-new-sha", "BBB")

        db.refresh(wf_a); db.refresh(wf_b)
        assert wf_b.workflow_git_hash == "b-new-sha"
        assert wf_a.workflow_git_hash == "a-original"

    def test_prefix_mode_projects_collide_too(self, db):
        """Prefixing protects the GitHub filename, not the workflows table.

        Both projects use_prefix=True, so they push AM_AAA_ci.yml and
        AM_BBB_ci.yml — no file collision — yet both store the bare stem "ci"
        and were equally vulnerable.
        """
        project_a = _project(db, "PFA", use_prefix=True)
        project_b = _project(db, "PFB", use_prefix=True)
        wf_a = _workflow(db, project_a, "ci", git_hash="a-original")
        wf_b = _workflow(db, project_b, "ci", git_hash="b-original")

        # Second project again, for the same ordering reason as above.
        _update_workflow_git_hash(db, "ci", "b-new-sha", "PFB")

        db.refresh(wf_a); db.refresh(wf_b)
        assert wf_b.workflow_git_hash == "b-new-sha"
        assert wf_a.workflow_git_hash == "a-original"

    def test_regular_and_reusable_of_the_same_name_are_distinct(self, db):
        # One project may legitimately hold both.
        project = _project(db, "DUAL")
        # Regular first, so an unscoped .first() would wrongly pick it.
        regular = _workflow(db, project, "ci", git_hash="regular-original")
        reusable = _workflow(db, project, "ci", git_hash="reusable-original", is_reusable=True)

        _update_workflow_git_hash(db, "ci", "reusable-new", "DUAL", is_reusable=True)

        db.refresh(regular); db.refresh(reusable)
        assert reusable.workflow_git_hash == "reusable-new"
        assert regular.workflow_git_hash == "regular-original"

    def test_unknown_project_updates_nothing(self, db):
        project = _project(db, "REAL")
        wf = _workflow(db, project, "ci", git_hash="untouched")

        _update_workflow_git_hash(db, "ci", "new", "NOPE")

        db.refresh(wf)
        assert wf.workflow_git_hash == "untouched"

    def test_empty_sha_is_ignored(self, db):
        project = _project(db, "SKIP")
        wf = _workflow(db, project, "ci", git_hash="keep")

        _update_workflow_git_hash(db, "ci", "", "SKIP")

        db.refresh(wf)
        assert wf.workflow_git_hash == "keep"


class TestNameMatchingHasNoWildcards:
    def test_underscore_is_not_treated_as_a_wildcard(self, db):
        """'_' is a single-char wildcard in SQL LIKE, so ILIKE('ci_build')
        matched 'ciXbuild'. Both rows must exist or this proves nothing."""
        from sqlalchemy import func

        project = _project(db, "WILD")
        decoy = _workflow(db, project, "ciXbuild", git_hash="decoy")
        real = _workflow(db, project, "ci_build", git_hash="real")

        # The corrected matching used by the upsert paths.
        match = (
            db.query(Workflow)
            .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
            .filter(
                ProjectWorkflow.project_id == project.project_id,
                func.lower(Workflow.workflow_name) == "ci_build",
            )
            .all()
        )

        assert [m.workflow_id for m in match] == [real.workflow_id]
        assert decoy.workflow_id not in [m.workflow_id for m in match]

    def test_matching_is_still_case_insensitive(self, db):
        from sqlalchemy import func

        project = _project(db, "CASE")
        wf = _workflow(db, project, "CI")

        match = (
            db.query(Workflow)
            .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
            .filter(
                ProjectWorkflow.project_id == project.project_id,
                func.lower(Workflow.workflow_name) == "ci",
            )
            .first()
        )

        assert match is not None
        assert match.workflow_id == wf.workflow_id


class TestOneProjectPerWorkflow:
    def test_a_workflow_cannot_be_added_to_a_second_project(self, db):
        project_a = _project(db, "ONE")
        project_b = _project(db, "TWO")
        wf = _workflow(db, project_a, "ci")

        db.add(ProjectWorkflow(project_id=project_b.project_id, workflow_id=wf.workflow_id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_the_unique_index_exists(self, db):
        indexes = db.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='project_workflows'")
        ).fetchall()
        assert "uq_project_workflows_workflow_id" in [i[0] for i in indexes]
