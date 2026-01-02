import argparse
import asyncio
import json
from datetime import datetime

import httpx

from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

# --- Configuration ---
API_BASE_URL = "http://localhost:8000"
ORG_ID = "01b6554c-4884-409f-a0e1-22e394bee989"


# --- Helper Functions ---
def get_headers(token: str) -> dict:
    """Returns standard request headers."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def authenticate() -> str:
    """Authenticates and returns a JWT token."""
    print("Authenticating to get JWT token...")
    try:
        if not settings.TEST_USER_EMAIL or not settings.TEST_USER_PASSWORD:
            raise ValueError("TEST_USER_EMAIL and TEST_USER_PASSWORD must be set")
        jwt_token = await asyncio.to_thread(
            get_user_jwt,
            settings.TEST_USER_EMAIL,
            settings.TEST_USER_PASSWORD,
        )
        print("✅ Authentication successful.")
        return jwt_token
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        exit(1)


def print_response(message, response):
    """Prints formatted request/response details."""
    print(f"--- {message} ---")
    print(f"Status Code: {response.status_code}")
    try:
        print("Response JSON:")
        print(json.dumps(response.json(), indent=2))
    except json.JSONDecodeError:
        print("Response Text:")
        print(response.text)
    print("-" * (len(message) + 8))
    print()
    response.raise_for_status()


# --- Test Workflow ---
async def run_cron_tests(org_id: str, project_id: str, client: httpx.AsyncClient):
    """Runs a full lifecycle test for the cron API."""
    created_cron_id = None
    try:
        # 1. Create a new Cron Job
        print("Running: 1. Create Cron Job")
        cron_payload = {
            "name": f"Test Cron Job - {datetime.now().isoformat()}",
            "cron_expr": "0 12 * * 1-5",  # Every weekday at 12:00
            "tz": "UTC",
            "entrypoint": "agent_inference",
            "payload": {
                "project_id": project_id,
                "env": "production",
                "input_data": {"messages": [{"role": "user", "content": "Test payload"}]},
            },
        }
        create_response = await client.post(f"{API_BASE_URL}/organizations/{org_id}/crons", json=cron_payload)
        print_response("1. Create Cron Job", create_response)
        created_cron_id = create_response.json()["id"]

        # 2. Get all Cron Jobs for the organization
        print("\nRunning: 2. List Cron Jobs")
        list_response = await client.get(f"{API_BASE_URL}/organizations/{org_id}/crons")
        print_response("2. List Cron Jobs", list_response)
        assert any(job["id"] == created_cron_id for job in list_response.json()["cron_jobs"])
        print("✅ Cron job found in the list.")

        # 3. Get details for the created Cron Job
        print("\nRunning: 3. Get Cron Job Details")
        detail_response = await client.get(f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}")
        print_response("3. Get Cron Job Details", detail_response)
        assert detail_response.json()["name"] == cron_payload["name"]

        # 4. Update the Cron Job
        print("\nRunning: 4. Update Cron Job")
        update_payload = {
            "name": f"Updated Cron Job Name - {datetime.now().isoformat()}",
            "cron_expr": "0 13 * * *",  # Daily at 13:00
        }
        update_response = await client.patch(
            f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}",
            json=update_payload,
        )
        print_response("4. Update Cron Job", update_response)
        assert update_response.json()["name"] == update_payload["name"]
        assert update_response.json()["cron_expr"] == update_payload["cron_expr"]

        # 5. Pause the Cron Job
        print("\nRunning: 5. Pause Cron Job")
        pause_response = await client.post(f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}/pause")
        print_response("5. Pause Cron Job", pause_response)
        assert not pause_response.json()["is_enabled"]

        # Verify it's inactive
        detail_after_pause = (
            await client.get(f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}")
        ).json()
        assert not detail_after_pause["is_enabled"]
        print("✅ Cron job is inactive.")

        # 6. Resume the Cron Job
        print("\nRunning: 6. Resume Cron Job")
        resume_response = await client.post(f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}/resume")
        print_response("6. Resume Cron Job", resume_response)
        assert resume_response.json()["is_enabled"]

        # Verify it's active again
        detail_after_resume = (
            await client.get(f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}")
        ).json()
        assert detail_after_resume["is_enabled"]
        print("✅ Cron job is active again.")

    except httpx.HTTPStatusError as e:
        print(f"❌ Test failed with HTTP Error: {e.response.text}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        # 7. Clean up by deleting the created Cron Job
        if created_cron_id:
            print("\nRunning: 7. Delete Cron Job (Cleanup)")
            delete_response = await client.delete(f"{API_BASE_URL}/organizations/{org_id}/crons/{created_cron_id}")
            print_response("7. Delete Cron Job (Cleanup)", delete_response)


async def main():
    """Main function to parse args and run tests."""
    parser = argparse.ArgumentParser(description="Test the Cron Job API endpoints.")
    parser.add_argument(
        "--org-id",
        required=False,
        help="The UUID of the organization to run tests against.",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="The UUID of the project to run tests against.",
    )
    args = parser.parse_args()

    jwt_token = await authenticate()
    headers = get_headers(jwt_token)

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        await run_cron_tests(args.org_id or ORG_ID, args.project_id, client)


if __name__ == "__main__":
    asyncio.run(main())
