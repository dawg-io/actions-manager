"""
Shared test fixtures and configuration for all admin tests.

This file ensures that all test files use the same database engine and session,
preventing issues with multiple database instances when running tests together.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import app and dependencies
import sys
import os

# Tests are development environments by definition. Setting this before
# importing ``main`` ensures the startup validator applies the permissive
# self-hosted-development rules instead of the strict production rules.
# (See backend/mode_validation.py for the production/development split.)
os.environ.setdefault("ENVIRONMENT", "development")

# Admin routes are cloud-only; mount them during tests so that test_admin.py,
# test_tier_upgrade_downgrade.py, and any other test that exercises /admin/*
# endpoints can reach them.  setdefault means an explicit env var still wins.
os.environ.setdefault("INSTALLATION_MODE", "cloud")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import Base
from admin import get_db
from auth import get_db as auth_get_db

# Create shared test database (in-memory for test isolation)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Override the database dependency once for all tests
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[auth_get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create test database tables once for all tests"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def cleanup_database():
    """Clean up database after each test"""
    yield
    # Clean up all data after each test
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                db.execute(table.delete())
            except Exception:
                # Table may not exist in this database instance
                pass
        db.commit()
    finally:
        db.close()


@pytest.fixture
def test_db():
    """Get test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
