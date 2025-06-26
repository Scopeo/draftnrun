#!/usr/bin/env python3
"""Load test runner script for FastAPI backend"""

import argparse
import subprocess
import sys
from pathlib import Path

from scripts.load_testing.utils.auth_helpers import validate_auth_setup


def run_locust_command(
    scenario: str, users: int, spawn_rate: int, duration: int, host: str, headless: bool = True
) -> bool:
    """
    Run Locust with the specified parameters

    Args:
        scenario: Test scenario ('basic', 'auth', 'heavy', 'all')
        users: Number of concurrent users to simulate
        spawn_rate: Rate of spawning users per second
        duration: Test duration in seconds
        host: Target host URL (e.g., 'http://localhost:8000')
        headless: Whether to run in headless mode (default: True)

    Returns:
        bool: True if the test completed successfully, False otherwise
    """

    # Map scenarios to Locust user classes
    scenario_map = {
        "basic": "BasicEndpointsUser",
        "auth": "AuthenticatedUser",
        "heavy": "HeavyLoadUser",
        "all": "",  # Run all user classes (mixed workload)
    }

    if scenario not in scenario_map:
        print(f"❌ Unknown scenario: {scenario}")
        print(f"Available scenarios: {list(scenario_map.keys())}")
        return False

    # Build Locust command
    cmd = [
        "locust",
        "-f",
        "locustfile.py",
        "--host",
        host,
        "--users",
        str(users),
        "--spawn-rate",
        str(spawn_rate),
        "--run-time",
        f"{duration}s",
    ]

    # Add user class if specific scenario
    if scenario != "all":
        cmd.extend([scenario_map[scenario]])

    # Add headless mode
    if headless:
        cmd.append("--headless")

    print(f"🚀 Starting load test...")
    print(f"   Scenario: {scenario}")
    print(f"   Users: {users}")
    print(f"   Spawn rate: {spawn_rate}/sec")
    print(f"   Duration: {duration}s")
    print(f"   Host: {host}")
    print(f"   Command: {' '.join(cmd)}")
    print()

    try:
        # Change to the load testing directory
        load_test_dir = Path(__file__).parent
        result = subprocess.run(cmd, cwd=load_test_dir, check=True)
        print("✅ Load test completed successfully!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Load test failed with exit code {e.returncode}")
        return False
    except KeyboardInterrupt:
        print("\n⏹️  Load test interrupted by user")
        return True
    except FileNotFoundError:
        print("❌ Locust not found. Install it with: pip install locust")
        return False


def validate_prerequisites() -> bool:
    """Validate that all prerequisites are met"""
    print("🔍 Validating prerequisites...")

    # Check if Locust is installed
    try:
        result = subprocess.run(["locust", "--version"], capture_output=True, text=True, check=True)
        print(f"✅ Locust installed: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Locust not installed. Install with: pip install locust")
        return False

    # Check if FastAPI is running
    try:
        import requests

        response = requests.get("http://localhost:8000/", timeout=5)
        if response.status_code == 200:
            print("✅ FastAPI server is running")
        else:
            print(f"⚠️  FastAPI server responded with status {response.status_code}")
    except requests.exceptions.RequestException:
        print("❌ FastAPI server not accessible at http://localhost:8000")
        print("   Make sure to start your FastAPI server first")
        return False
    except ImportError:
        print("⚠️  requests not installed, skipping server check")

    print("✅ Prerequisites validation completed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run load tests against FastAPI backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic demo (10 users, 2/sec spawn rate, 60 seconds)
    python run_load_test.py --scenario basic --users 10 --spawn-rate 2 --duration 60
    
    # Authenticated testing (5 users, 1/sec spawn rate, 2 minutes)
    python run_load_test.py --scenario auth --users 5 --spawn-rate 1 --duration 120
    
    # Heavy load testing (2 users, 1/sec spawn rate, 30 seconds)
    python run_load_test.py --scenario heavy --users 2 --spawn-rate 1 --duration 30
    
    # Mixed workload (all scenarios)
    python run_load_test.py --scenario all --users 15 --spawn-rate 3 --duration 180
    
    # Interactive mode (opens web UI)
    python run_load_test.py --scenario basic --interactive
        """,
    )

    parser.add_argument(
        "--scenario", choices=["basic", "auth", "heavy", "all"], default="basic", help="Load test scenario to run"
    )

    parser.add_argument("--users", type=int, default=10, help="Number of concurrent users (default: 10)")

    parser.add_argument("--spawn-rate", type=int, default=2, help="User spawn rate per second (default: 2)")

    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds (default: 60)")

    parser.add_argument(
        "--host", default="http://localhost:8000", help="Target host URL (default: http://localhost:8000)"
    )

    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode (opens web UI)")

    parser.add_argument("--skip-validation", action="store_true", help="Skip prerequisite validation")

    args = parser.parse_args()

    print("🔥 FastAPI Load Testing Script")
    print("=" * 50)

    # Validate prerequisites
    if not args.skip_validation:
        if not validate_prerequisites():
            print("\n❌ Prerequisites not met. Fix the issues above and try again.")
            sys.exit(1)
        print()

    # Validate auth setup for authenticated scenarios
    if args.scenario in ["auth", "heavy", "all"]:
        print("🔐 Validating authentication setup...")
        if not validate_auth_setup():
            print("\n❌ Authentication setup failed.")
            print("   For authenticated scenarios, make sure your credentials are configured.")
            print("   You can still run the 'basic' scenario without authentication.")
            sys.exit(1)
        print()

    # Run the load test
    success = run_locust_command(
        scenario=args.scenario,
        users=args.users,
        spawn_rate=args.spawn_rate,
        duration=args.duration,
        host=args.host,
        headless=not args.interactive,
    )

    if success:
        print("\n🎉 Load test completed!")
        print("📊 Check your Grafana dashboard at http://localhost:3000")
        print("   to see the performance metrics and impact!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
