#!/usr/bin/env python3
"""FastAPI Load Testing Runner Script"""

import argparse
import subprocess
import sys
from pathlib import Path

import requests


def validate_prerequisites() -> bool:
    """Validate that all prerequisites are met"""
    print("🔍 Validating prerequisites...")

    # Check if locust is installed
    try:
        result = subprocess.run(["locust", "--version"], capture_output=True, text=True, check=True)
        print(f"✅ Locust installed: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Locust is not installed or not accessible")
        print("   Install with: uv sync --group load_testing")
        return False

    # Check if FastAPI server is running
    try:

        response = requests.get("http://localhost:8000/", timeout=5)
        if response.status_code == 200:
            print("✅ FastAPI server is running")
        else:
            print(f"❌ FastAPI server returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ FastAPI server is not accessible: {e}")
        print("   Make sure your FastAPI server is running on http://localhost:8000")
        return False

    print("✅ Prerequisites validation completed")
    return True


def run_locust_command(
    users: int,
    spawn_rate: int,
    duration: int,
    host: str,
    interactive: bool,
    skip_validation: bool,
) -> None:
    """Run the locust command with specified parameters"""
    if not skip_validation:
        if not validate_prerequisites():
            sys.exit(1)

    print("\n🚀 Starting load test...")
    print(f"   Users: {users}")
    print(f"   Spawn rate: {spawn_rate}/sec")
    print(f"   Duration: {duration}s")
    print(f"   Host: {host}")

    # Build the locust command
    locust_path = Path(__file__).parent / "locustfile.py"
    cmd = [
        "locust",
        "-f",
        str(locust_path),
        "--host",
        host,
        "--users",
        str(users),
        "--spawn-rate",
        str(spawn_rate),
        "BasicEndpointsUser",
    ]

    # Add duration for headless mode
    if not interactive:
        cmd.extend(["--run-time", f"{duration}s"])
        cmd.append("--headless")

    print(f"   Command: {' '.join(cmd)}")

    # Run the command
    try:
        subprocess.run(cmd, check=True)
        print("\n✅ Load test completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Load test failed with exit code: {e.returncode}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Load test interrupted by user")
        sys.exit(1)

    print("\n🎉 Load test completed!")
    print("📊 Check your Grafana dashboard at http://localhost:3000")
    print("   to see the performance metrics and impact!")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run load tests against FastAPI backend",
        epilog="""
Examples:
    # Basic demo (10 users, 2/sec spawn rate, 60 seconds)
    python run_load_test.py --users 10 --spawn-rate 2 --duration 60

    # High load testing (25 users, 5/sec spawn rate, 30 seconds)
    python run_load_test.py --users 25 --spawn-rate 5 --duration 30

    # Interactive mode (opens web UI)
    python run_load_test.py --users 10 --interactive
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--users",
        type=int,
        default=10,
        help="Number of concurrent users (default: 10)",
    )
    parser.add_argument(
        "--spawn-rate",
        type=int,
        default=2,
        help="User spawn rate per second (default: 2)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:8000",
        help="Target host URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode (opens web UI)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip prerequisite validation",
    )

    args = parser.parse_args()

    print("🔥 FastAPI Load Testing Script")
    print("=" * 50)

    run_locust_command(
        users=args.users,
        spawn_rate=args.spawn_rate,
        duration=args.duration,
        host=args.host,
        interactive=args.interactive,
        skip_validation=args.skip_validation,
    )


if __name__ == "__main__":
    main()
