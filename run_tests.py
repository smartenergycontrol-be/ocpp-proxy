#!/usr/bin/env python3
"""
Test runner script for OCPP Proxy application.

This script provides various options for running the test suite:
- Run all tests
- Run specific test categories (unit, integration, e2e)
- Run with coverage reporting
- Run with different verbosity levels
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{description}")
    print("=" * len(description))
    print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"❌ {description} failed with exit code {result.returncode}")
        return False
    else:
        print(f"✅ {description} completed successfully")
        return True


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Run OCPP Proxy test suite")
    
    # Test type options
    parser.add_argument(
        "--unit", 
        action="store_true", 
        help="Run only unit tests"
    )
    parser.add_argument(
        "--integration", 
        action="store_true", 
        help="Run only integration tests"
    )
    parser.add_argument(
        "--e2e", 
        action="store_true", 
        help="Run only end-to-end tests"
    )
    parser.add_argument(
        "--slow", 
        action="store_true", 
        help="Include slow tests"
    )
    
    # Coverage options
    parser.add_argument(
        "--no-coverage", 
        action="store_true", 
        help="Disable coverage reporting"
    )
    parser.add_argument(
        "--coverage-html", 
        action="store_true", 
        help="Generate HTML coverage report"
    )
    
    # Output options
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true", 
        help="Verbose output"
    )
    parser.add_argument(
        "--quiet", "-q", 
        action="store_true", 
        help="Quiet output"
    )
    
    # Specific test options
    parser.add_argument(
        "--file", 
        type=str, 
        help="Run specific test file"
    )
    parser.add_argument(
        "--function", 
        type=str, 
        help="Run specific test function"
    )
    
    # Other options
    parser.add_argument(
        "--install-deps", 
        action="store_true", 
        help="Install test dependencies before running tests"
    )
    parser.add_argument(
        "--parallel", 
        action="store_true", 
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--stop-on-failure", 
        action="store_true", 
        help="Stop on first failure"
    )
    
    args = parser.parse_args()
    
    # Change to project root directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Install dependencies if requested
    if args.install_deps:
        if not run_command([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], "Installing test dependencies"):
            return 1
    
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Add test selection markers
    markers = []
    if args.unit:
        markers.append("unit")
    if args.integration:
        markers.append("integration")
    if args.e2e:
        markers.append("e2e")
    
    if markers:
        cmd.extend(["-m", " or ".join(markers)])
    
    # Add slow tests if requested
    if not args.slow:
        if markers:
            cmd.extend(["-m", f"({' or '.join(markers)}) and not slow"])
        else:
            cmd.extend(["-m", "not slow"])
    
    # Add verbosity options
    if args.verbose:
        cmd.append("-v")
    elif args.quiet:
        cmd.append("-q")
    
    # Add coverage options
    if not args.no_coverage:
        cmd.extend([
            "--cov=src/ev_charger_proxy",
            "--cov-report=term-missing"
        ])
        
        if args.coverage_html:
            cmd.extend(["--cov-report=html:htmlcov"])
    
    # Add parallel execution
    if args.parallel:
        try:
            import pytest_xdist
            cmd.extend(["-n", "auto"])
        except ImportError:
            print("⚠️  pytest-xdist not installed. Running tests sequentially.")
    
    # Add stop on failure
    if args.stop_on_failure:
        cmd.append("-x")
    
    # Add specific file or function
    if args.file:
        if args.function:
            cmd.append(f"{args.file}::{args.function}")
        else:
            cmd.append(args.file)
    elif args.function:
        cmd.extend(["-k", args.function])
    
    # Add test directory if no specific file
    if not args.file:
        cmd.append("tests/")
    
    # Run the tests
    success = run_command(cmd, "Running test suite")
    
    if success:
        print("\n🎉 All tests passed!")
        
        if not args.no_coverage and not args.coverage_html:
            print("\n📊 Coverage report generated in terminal above")
        
        if args.coverage_html:
            print("📊 HTML coverage report generated in htmlcov/index.html")
        
        return 0
    else:
        print("\n💥 Tests failed!")
        return 1


def run_specific_test_suites():
    """Run predefined test suites."""
    print("OCPP Proxy Test Suite Runner")
    print("=" * 40)
    
    # Quick test suite (unit tests only)
    print("\n1. Quick Test Suite (Unit Tests)")
    quick_success = run_command([
        sys.executable, "-m", "pytest", 
        "-m", "unit", 
        "--cov=src/ev_charger_proxy",
        "--cov-report=term-missing",
        "tests/"
    ], "Quick test suite")
    
    if not quick_success:
        return 1
    
    # Full test suite (all tests)
    print("\n2. Full Test Suite (All Tests)")
    full_success = run_command([
        sys.executable, "-m", "pytest", 
        "--cov=src/ev_charger_proxy",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "tests/"
    ], "Full test suite")
    
    if full_success:
        print("\n🎉 All test suites passed!")
        print("📊 HTML coverage report: htmlcov/index.html")
        return 0
    else:
        print("\n💥 Some tests failed!")
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # No arguments provided, run predefined suites
        sys.exit(run_specific_test_suites())
    else:
        # Arguments provided, use argument parser
        sys.exit(main())