"""
Tests for campaign notification event emission (issue #1794, part of #1789).

Unit-tests the diff/emit functions directly: old-state -> new-state pairs,
asserting which events fire and that routine/repeat calls don't re-emit.
"""

import sys
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, ProjectPRCampaign, ProjectPullRequest, NotificationEvent
from campaign_notifications import (
    record_campaign_opened,
    record_campaign_pr_transition,
    record_campaign_status_transition,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _setup_project_and_campaign(db):
    account = Account(github_user="campaignuser", github_email="campaign@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(project_name="campaign_project", project_code="CMP", user_id=account.user_id)
    db.add(project)
    db.commit()
    db.refresh(project)

    campaign = ProjectPRCampaign(project_id=project.project_id, created_by="campaignuser")
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return project, campaign


def _make_pr(db, project, campaign, pr_number=1, pr_state="open"):
    pr = ProjectPullRequest(
        project_id=project.project_id,
        campaign_id=campaign.campaign_id,
        repo_name="acme/widgets",
        pr_number=pr_number,
        pr_url=f"https://github.com/acme/widgets/pull/{pr_number}",
        pr_state=pr_state,
        branch_name="actions-manager/cmp-main",
        target_branch="main",
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return pr


class TestRecordCampaignOpened:
    def test_all_created_emits_only_opened_event(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)
        results = {
            "acme/widgets on main": {"status": "pr_created"},
            "acme/gadgets on main": {"status": "pr_created"},
        }

        record_campaign_opened(db_session, project, campaign, results)

        events = db_session.query(NotificationEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "campaign.opened"

    def test_partial_failure_emits_opened_partially_failed_and_per_repo_failed(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)
        results = {
            "acme/widgets on main": {"status": "pr_created"},
            "acme/broken on main": {"status": "error", "error": "branch protection blocked push"},
        }

        record_campaign_opened(db_session, project, campaign, results)

        events = {e.event_type for e in db_session.query(NotificationEvent).all()}
        assert events == {"campaign.opened", "campaign.partially_failed", "campaign_pr.failed"}

    def test_all_failed_does_not_emit_partially_failed(self, db_session):
        """No successes to contrast against — this is a total failure, not a partial one."""
        project, campaign = _setup_project_and_campaign(db_session)
        results = {
            "acme/broken on main": {"status": "error", "error": "branch protection blocked push"},
        }

        record_campaign_opened(db_session, project, campaign, results)

        events = {e.event_type for e in db_session.query(NotificationEvent).all()}
        assert "campaign.partially_failed" not in events
        assert "campaign_pr.failed" in events

    def test_reprocessing_same_campaign_does_not_duplicate_events(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)
        results = {"acme/widgets on main": {"status": "pr_created"}}

        record_campaign_opened(db_session, project, campaign, results)
        record_campaign_opened(db_session, project, campaign, results)

        assert db_session.query(NotificationEvent).count() == 1


class TestRecordCampaignPrTransition:
    def test_open_to_merged_emits_event(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)
        pr = _make_pr(db_session, project, campaign)

        record_campaign_pr_transition(db_session, pr, "open", "merged")

        events = db_session.query(NotificationEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "campaign_pr.merged"

    def test_open_to_closed_emits_event(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)
        pr = _make_pr(db_session, project, campaign)

        record_campaign_pr_transition(db_session, pr, "open", "closed")

        events = db_session.query(NotificationEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "campaign_pr.closed"

    def test_non_open_starting_state_does_not_emit(self, db_session):
        """Terminal states are one-way; a state that was never 'open' here isn't a real transition."""
        project, campaign = _setup_project_and_campaign(db_session)
        pr = _make_pr(db_session, project, campaign)

        record_campaign_pr_transition(db_session, pr, "merged", "merged")

        assert db_session.query(NotificationEvent).count() == 0

    def test_pr_without_campaign_does_not_emit(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)
        pr = _make_pr(db_session, project, campaign)
        pr.campaign_id = None

        record_campaign_pr_transition(db_session, pr, "open", "merged")

        assert db_session.query(NotificationEvent).count() == 0


class TestRecordCampaignStatusTransition:
    def test_open_to_completed_emits_event(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)

        record_campaign_status_transition(
            db_session, project.project_id, project.project_name, campaign, "completed", 0, 2, 0
        )

        events = db_session.query(NotificationEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "campaign.completed"
        assert campaign.last_known_status == "completed"

    def test_still_open_does_not_emit(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)

        record_campaign_status_transition(
            db_session, project.project_id, project.project_name, campaign, "open", 1, 1, 0
        )

        assert db_session.query(NotificationEvent).count() == 0

    def test_repeated_read_after_completion_does_not_reemit(self, db_session):
        project, campaign = _setup_project_and_campaign(db_session)

        record_campaign_status_transition(
            db_session, project.project_id, project.project_name, campaign, "partially_completed", 0, 1, 1
        )
        record_campaign_status_transition(
            db_session, project.project_id, project.project_name, campaign, "partially_completed", 0, 1, 1
        )

        assert db_session.query(NotificationEvent).count() == 1
