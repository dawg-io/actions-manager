#!/usr/bin/env python3
"""
Comprehensive QA Test Runner for Actions Manager

This script runs all QA tests for:
1. License validation scenarios (expired, invalid, upgrade/downgrade)
2. Docker deployment configurations (self-hosted and cloud)
3. Install script validation
4. Tier gate enforcement
5. Common error scenarios

Generates a comprehensive test report with pass/fail status for each category.
"""

import sys
import os
import subprocess
import json
from datetime import datetime
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_path))


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}\n")


def print_section(text):
    """Print formatted section"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}▶ {text}{Colors.END}")
    print(f"{Colors.BLUE}{'-' * 80}{Colors.END}")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_failure(text):
    """Print failure message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def run_pytest_suite(test_file, suite_name):
    """
    Run a pytest test file and return results
    
    Args:
        test_file: Path to test file
        suite_name: Name of the test suite
        
    Returns:
        dict: Test results with pass/fail counts
    """
    print_section(f"Running {suite_name}")
    
    # Check if test file exists
    if not os.path.exists(test_file):
        print_failure(f"Test file not found: {test_file}")
        return {
            'suite': suite_name,
            'passed': 0,
            'failed': 0,
            'total': 0,
            'skipped': 0,
            'duration': 0,
            'status': 'error',
            'error': 'Test file not found'
        }
    
    # Run pytest with JSON output
    cmd = [
        'python', '-m', 'pytest',
        test_file,
        '-v',
        '--tb=short',
        '--json-report',
        '--json-report-file=/tmp/pytest_report.json'
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        
        # Parse results from stdout
        output = result.stdout
        
        # Extract test counts from pytest output
        passed = output.count(' PASSED')
        failed = output.count(' FAILED')
        skipped = output.count(' SKIPPED')
        total = passed + failed + skipped
        
        status = 'passed' if failed == 0 else 'failed'
        
        # Try to read JSON report if available
        json_report_path = '/tmp/pytest_report.json'
        duration = 0
        if os.path.exists(json_report_path):
            try:
                with open(json_report_path, 'r') as f:
                    json_data = json.load(f)
                    duration = json_data.get('duration', 0)
            except:
                pass
        
        # Print summary
        if status == 'passed':
            print_success(f"{suite_name}: {passed}/{total} tests passed")
        else:
            print_failure(f"{suite_name}: {failed}/{total} tests failed")
        
        if skipped > 0:
            print_warning(f"{suite_name}: {skipped} tests skipped")
        
        return {
            'suite': suite_name,
            'passed': passed,
            'failed': failed,
            'total': total,
            'skipped': skipped,
            'duration': duration,
            'status': status,
            'output': output
        }
        
    except Exception as e:
        print_failure(f"Error running {suite_name}: {str(e)}")
        return {
            'suite': suite_name,
            'passed': 0,
            'failed': 0,
            'total': 0,
            'skipped': 0,
            'duration': 0,
            'status': 'error',
            'error': str(e)
        }


def run_all_qa_tests():
    """Run all QA test suites"""
    print_header("ACTIONS MANAGER - COMPREHENSIVE QA TEST SUITE")
    
    start_time = datetime.now()
    
    # Define test suites
    test_suites = [
        {
            'file': 'backend/tests/test_qa_licensing_scenarios.py',
            'name': 'License Validation Scenarios'
        },
        {
            'file': 'backend/tests/test_qa_deployment_validation.py',
            'name': 'Docker Deployment Validation'
        },
        {
            'file': 'backend/tests/test_license.py',
            'name': 'Core License Validation'
        },
        {
            'file': 'backend/tests/test_tier_upgrade_downgrade.py',
            'name': 'Account Tier Upgrade/Downgrade'
        },
        {
            'file': 'backend/tests/test_self_hosted_license_types.py',
            'name': 'Self-Hosted License Types'
        }
    ]
    
    results = []
    
    # Run each test suite
    for suite in test_suites:
        result = run_pytest_suite(suite['file'], suite['name'])
        results.append(result)
    
    # Calculate totals
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()
    
    total_passed = sum(r['passed'] for r in results)
    total_failed = sum(r['failed'] for r in results)
    total_skipped = sum(r['skipped'] for r in results)
    total_tests = sum(r['total'] for r in results)
    
    # Print summary report
    print_header("QA TEST SUMMARY REPORT")
    
    print(f"Execution Time: {total_duration:.2f} seconds")
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Print results by suite
    print_section("Results by Test Suite")
    for result in results:
        suite_name = result['suite']
        status = result['status']
        passed = result['passed']
        failed = result['failed']
        total = result['total']
        
        if status == 'passed':
            print_success(f"{suite_name}: {passed}/{total} passed")
        elif status == 'failed':
            print_failure(f"{suite_name}: {failed}/{total} failed, {passed}/{total} passed")
        else:
            print_warning(f"{suite_name}: Error running tests")
    
    # Print overall statistics
    print_section("Overall Statistics")
    print(f"Total Tests Run: {total_tests}")
    print(f"Total Passed: {Colors.GREEN}{total_passed}{Colors.END}")
    print(f"Total Failed: {Colors.RED}{total_failed}{Colors.END}")
    if total_skipped > 0:
        print(f"Total Skipped: {Colors.YELLOW}{total_skipped}{Colors.END}")
    
    if total_tests > 0:
        pass_rate = (total_passed / total_tests) * 100
        print(f"Pass Rate: {pass_rate:.1f}%")
    
    # Print acceptance criteria status
    print_section("Acceptance Criteria Validation")
    
    criteria = [
        {
            'name': 'All tier checks function',
            'passed': any(r['suite'] == 'Core License Validation' and r['status'] == 'passed' for r in results)
        },
        {
            'name': 'Both compose files/setup work',
            'passed': any(r['suite'] == 'Docker Deployment Validation' and r['status'] == 'passed' for r in results)
        },
        {
            'name': 'License key handling robust',
            'passed': any(r['suite'] == 'License Validation Scenarios' and r['status'] == 'passed' for r in results)
        },
        {
            'name': 'Upgrade/downgrade paths validated',
            'passed': any(r['suite'] == 'Account Tier Upgrade/Downgrade' and r['status'] == 'passed' for r in results)
        }
    ]
    
    all_criteria_passed = True
    for criterion in criteria:
        if criterion['passed']:
            print_success(criterion['name'])
        else:
            print_failure(criterion['name'])
            all_criteria_passed = False
    
    # Final status
    print()
    if total_failed == 0 and all_criteria_passed:
        print_header("✓ ALL QA TESTS PASSED")
        return 0
    else:
        print_header("✗ SOME QA TESTS FAILED")
        return 1


def main():
    """Main entry point"""
    try:
        exit_code = run_all_qa_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {str(e)}{Colors.END}")
        sys.exit(1)


if __name__ == "__main__":
    main()
