"""
Tests for admin module helper functions

Tests the refactored helper functions to ensure they work correctly in isolation.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import app and dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base
from models import Account
from admin import (
    validate_pagination_params,
    validate_sort_params,
    build_user_query,
    calculate_pagination_info,
    format_user_row,
    generate_html_header,
    generate_user_rows_html,
    generate_html_footer,
    create_secure_response
)

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def setup_database():
    """Create test database and tables before each test"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_db():
    """Get test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestValidatePaginationParams:
    """Test pagination parameter validation"""
    
    def test_valid_params(self):
        """Test with valid parameters"""
        page, per_page = validate_pagination_params(2, 100)
        assert page == 2
        assert per_page == 100
    
    def test_negative_page(self):
        """Test that negative page numbers are corrected to 1"""
        page, per_page = validate_pagination_params(-1, 50)
        assert page == 1
        assert per_page == 50
    
    def test_zero_page(self):
        """Test that zero page is corrected to 1"""
        page, per_page = validate_pagination_params(0, 50)
        assert page == 1
    
    def test_negative_per_page(self):
        """Test that negative per_page is corrected to 1"""
        page, per_page = validate_pagination_params(1, -10)
        assert per_page == 1
    
    def test_per_page_exceeds_max(self):
        """Test that per_page over 200 is capped"""
        page, per_page = validate_pagination_params(1, 300)
        assert per_page == 200
    
    def test_edge_case_200(self):
        """Test that per_page of exactly 200 is allowed"""
        page, per_page = validate_pagination_params(1, 200)
        assert per_page == 200


class TestValidateSortParams:
    """Test sort parameter validation"""
    
    def test_valid_sort_params(self):
        """Test with valid sort parameters"""
        sort_by, sort_order = validate_sort_params('user_id', 'asc')
        assert sort_by == 'user_id'
        assert sort_order == 'asc'
    
    def test_invalid_sort_column(self):
        """Test that invalid column defaults to last_login_at"""
        sort_by, sort_order = validate_sort_params('invalid_column', 'desc')
        assert sort_by == 'last_login_at'
        assert sort_order == 'desc'
    
    def test_invalid_sort_order(self):
        """Test that invalid order defaults to desc"""
        sort_by, sort_order = validate_sort_params('user_id', 'invalid')
        assert sort_by == 'user_id'
        assert sort_order == 'desc'
    
    def test_all_valid_columns(self):
        """Test all valid sort columns"""
        valid_columns = [
            'user_id', 'github_user', 'github_email', 'account_type',
            'github_account_type', 'last_login_at', 'github_api_calls', 'github_api_calls_today'
        ]
        
        for column in valid_columns:
            sort_by, sort_order = validate_sort_params(column, 'asc')
            assert sort_by == column


class TestBuildUserQuery:
    """Test database query building"""
    
    def test_query_with_desc_order(self, setup_database, test_db):
        """Test query builds with descending order"""
        query = build_user_query(test_db, 'user_id', 'desc')
        assert query is not None
    
    def test_query_with_asc_order(self, setup_database, test_db):
        """Test query builds with ascending order"""
        query = build_user_query(test_db, 'user_id', 'asc')
        assert query is not None


class TestCalculatePaginationInfo:
    """Test pagination calculation"""
    
    def test_single_page(self):
        """Test with data that fits on one page"""
        info = calculate_pagination_info(10, 1, 50)
        assert info['total_pages'] == 1
        assert info['has_prev'] is False
        assert info['has_next'] is False
    
    def test_multiple_pages(self):
        """Test with data spanning multiple pages"""
        info = calculate_pagination_info(100, 1, 50)
        assert info['total_pages'] == 2
        assert info['has_prev'] is False
        assert info['has_next'] is True
    
    def test_middle_page(self):
        """Test when on a middle page"""
        info = calculate_pagination_info(150, 2, 50)
        assert info['total_pages'] == 3
        assert info['has_prev'] is True
        assert info['has_next'] is True
    
    def test_last_page(self):
        """Test when on the last page"""
        info = calculate_pagination_info(100, 2, 50)
        assert info['total_pages'] == 2
        assert info['has_prev'] is True
        assert info['has_next'] is False
    
    def test_empty_data(self):
        """Test with zero users"""
        info = calculate_pagination_info(0, 1, 50)
        assert info['total_pages'] == 1
        assert info['has_prev'] is False
        assert info['has_next'] is False


class TestFormatUserRow:
    """Test user data formatting"""
    
    def test_format_complete_user(self):
        """Test formatting user with all fields"""
        user = Account(
            user_id=1,
            github_user="testuser",
            github_email="test@example.com",
            account_type="enterprise",
            github_account_type="User",
            avatar_url="https://example.com/avatar.jpg",
            last_login_at=datetime(2024, 1, 15, 10, 30, 0),
            last_login_ip="192.168.1.1",
            github_api_calls=100,
            github_api_calls_today=10
        )
        
        data = format_user_row(user)
        
        assert data['user_id'] == 1
        assert 'testuser' in data['github_user']
        assert 'test@example.com' in data['github_email']
        assert 'enterprise' in data['account_type_badge']
        assert 'User' in data['github_account_type']
        assert 'https://example.com/avatar.jpg' in data['avatar_html']
        assert '2024-01-15' in data['last_login']
        assert '192.168.1.1' in data['last_login_ip']
        assert data['api_calls_total'] == 100
        assert data['api_calls_today'] == 10
    
    def test_format_user_with_nulls(self):
        """Test formatting user with null fields"""
        user = Account(
            user_id=2,
            github_user=None,
            github_email=None,
            account_type=None,
            github_account_type=None,
            avatar_url=None,
            last_login_at=None,
            last_login_ip=None,
            github_api_calls=None,
            github_api_calls_today=None
        )
        
        data = format_user_row(user)
        
        assert data['user_id'] == 2
        assert 'null-value' in data['github_user']
        assert 'null-value' in data['github_email']
        assert 'unknown' in data['account_type_badge']
        assert 'null-value' in data['github_account_type']
        assert 'null-value' in data['avatar_html']
        assert 'null-value' in data['last_login']
        assert 'null-value' in data['last_login_ip']
        assert data['api_calls_total'] == 0
        assert data['api_calls_today'] == 0
    
    def test_xss_protection(self):
        """Test that HTML is escaped in user data"""
        user = Account(
            user_id=3,
            github_user="<script>xss</script>",
            github_email="<img src=x onerror=alert('xss')>",
            account_type="professional",
            github_account_type="User",
            avatar_url=None,
            last_login_at=None,
            last_login_ip="<script>xss</script>",
            github_api_calls=0,
            github_api_calls_today=0
        )
        
        data = format_user_row(user)
        
        # Check that HTML is escaped
        assert '&lt;script&gt;' in data['github_user']
        assert '<script>' not in data['github_user']
        assert '&lt;img' in data['github_email']
        assert '<img src=x onerror=' not in data['github_email']
        assert '&lt;script&gt;' in data['last_login_ip']


class TestGenerateUserRowsHtml:
    """Test HTML generation for user rows"""
    
    def test_empty_user_list(self):
        """Test with empty user list"""
        html = generate_user_rows_html([])
        assert 'No users found' in html
    
    def test_single_user(self):
        """Test with one user"""
        user = Account(
            user_id=1,
            github_user="testuser",
            github_email="test@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url=None,
            last_login_at=None,
            last_login_ip=None,
            github_api_calls=0,
            github_api_calls_today=0
        )
        
        html = generate_user_rows_html([user])
        assert '<tr>' in html
        assert 'testuser' in html
        assert 'test@example.com' in html


class TestGenerateHtmlHeader:
    """Test HTML header generation"""
    
    def test_header_contains_stats(self):
        """Test that header includes statistics"""
        html = generate_html_header(100, 2, 50, 2, 'user_id', 'asc')
        assert '100' in html  # total users
        assert '2 / 2' in html  # Page 2 of 2
        assert 'Per Page' in html
    
    def test_header_contains_controls(self):
        """Test that header includes sort controls"""
        html = generate_html_header(100, 1, 50, 2, 'last_login_at', 'desc')
        assert 'sort-by' in html
        assert 'sort-order' in html
        assert 'per-page' in html


class TestGenerateHtmlFooter:
    """Test HTML footer generation"""
    
    def test_footer_with_pagination(self):
        """Test footer includes pagination controls"""
        pagination_info = {
            'total_pages': 3,
            'has_prev': True,
            'has_next': True
        }
        
        html = generate_html_footer(2, 50, 'user_id', 'asc', pagination_info)
        assert 'Previous' in html
        assert 'Next' in html
        assert 'Page 2 of 3' in html
    
    def test_footer_first_page(self):
        """Test footer on first page"""
        pagination_info = {
            'total_pages': 2,
            'has_prev': False,
            'has_next': True
        }
        
        html = generate_html_footer(1, 50, 'user_id', 'asc', pagination_info)
        assert 'disabled' in html  # Previous button should be disabled


class TestCreateSecureResponse:
    """Test response creation with security headers"""
    
    def test_response_has_security_headers(self):
        """Test that response includes all security headers"""
        response = create_secure_response("<html>Test</html>")
        
        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/html; charset=utf-8'
        assert 'no-store' in response.headers['cache-control']
        assert response.headers['x-robots-tag'] == 'noindex, nofollow'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['x-frame-options'] == 'DENY'
    
    def test_response_content(self):
        """Test that response contains the HTML content"""
        test_content = "<html><body>Test Content</body></html>"
        response = create_secure_response(test_content)
        assert test_content in response.body.decode('utf-8')


class TestWebhookFilterFormGeneration:
    """Test webhook filter form HTML generation"""
    
    def test_filter_form_with_no_filters(self):
        """Test filter form generation with no filters selected"""
        from admin import generate_webhook_filter_form_html
        
        html = generate_webhook_filter_form_html(None, None, None, 50)
        
        # Check that "All Events" is selected for processed filter
        assert 'value="" selected>All Events</option>' in html
        # Check that "All Actions" is selected for action filter
        assert 'value="" selected>All Actions</option>' in html
        # Check that no user value is present
        assert 'value=""' in html
        # Check that per_page 50 is selected
        assert 'value="50" selected>50</option>' in html
    
    def test_filter_form_with_processed_filter(self):
        """Test filter form with processed filter selected"""
        from admin import generate_webhook_filter_form_html
        
        html = generate_webhook_filter_form_html('true', None, None, 50)
        
        # Check that "Processed" is selected
        assert 'value="true" selected>Processed</option>' in html
        # Check that "All Events" is NOT selected
        assert 'value="" selected>All Events</option>' not in html
    
    def test_filter_form_with_action_filter(self):
        """Test filter form with action filter selected"""
        from admin import generate_webhook_filter_form_html
        
        html = generate_webhook_filter_form_html(None, 'purchased', None, 100)
        
        # Check that "Purchased" is selected
        assert 'value="purchased" selected>Purchased</option>' in html
        # Check that per_page 100 is selected
        assert 'value="100" selected>100</option>' in html
    
    def test_filter_form_with_user_filter(self):
        """Test filter form with GitHub user filter"""
        from admin import generate_webhook_filter_form_html
        
        html = generate_webhook_filter_form_html(None, None, 'testuser', 50)
        
        # Check that user value is present and escaped
        assert 'value="testuser"' in html
    
    def test_filter_form_xss_protection(self):
        """Test that filter form escapes malicious input"""
        from admin import generate_webhook_filter_form_html
        
        html = generate_webhook_filter_form_html(None, None, '<script>alert("xss")</script>', 50)
        
        # Check that the script tags are escaped
        assert '<script>' not in html
        assert '&lt;script&gt;' in html or '&amp;lt;script&amp;gt;' in html


class TestWebhookPaginationGeneration:
    """Test webhook pagination HTML generation"""
    
    def test_pagination_first_page(self):
        """Test pagination on the first page"""
        from admin import generate_webhook_pagination_html
        
        pagination_info = {
            'has_prev': False,
            'has_next': True,
            'total_pages': 5
        }
        
        html = generate_webhook_pagination_html(1, 50, pagination_info, '')
        
        # Check that previous link is disabled
        assert 'href="#" class="disabled"' in html or 'href="#"' in html and 'disabled' in html
        # Check that next link is active
        assert 'href="?page=2&per_page=50"' in html
        # Check page info
        assert 'Page 1 of 5' in html
    
    def test_pagination_middle_page(self):
        """Test pagination on a middle page"""
        from admin import generate_webhook_pagination_html
        
        pagination_info = {
            'has_prev': True,
            'has_next': True,
            'total_pages': 5
        }
        
        html = generate_webhook_pagination_html(3, 50, pagination_info, '')
        
        # Check that both links are active
        assert 'href="?page=2&per_page=50"' in html
        assert 'href="?page=4&per_page=50"' in html
        # Check page info
        assert 'Page 3 of 5' in html
    
    def test_pagination_last_page(self):
        """Test pagination on the last page"""
        from admin import generate_webhook_pagination_html
        
        pagination_info = {
            'has_prev': True,
            'has_next': False,
            'total_pages': 5
        }
        
        html = generate_webhook_pagination_html(5, 50, pagination_info, '')
        
        # Check that previous link is active
        assert 'href="?page=4&per_page=50"' in html
        # Check that next link is disabled
        assert 'class="disabled"' in html
        # Check page info
        assert 'Page 5 of 5' in html
    
    def test_pagination_with_filters(self):
        """Test pagination preserves filter parameters"""
        from admin import generate_webhook_pagination_html
        
        pagination_info = {
            'has_prev': True,
            'has_next': True,
            'total_pages': 3
        }
        
        filter_string = '&processed=true&action=purchased'
        html = generate_webhook_pagination_html(2, 100, pagination_info, filter_string)
        
        # Check that filter string is included in URLs
        assert 'href="?page=1&per_page=100&processed=true&action=purchased"' in html
        assert 'href="?page=3&per_page=100&processed=true&action=purchased"' in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
