import argparse
import asyncio
import httpx
from uuid import UUID

from ada_backend.scripts.cron.test_cron_crud import (
    authenticate,
    API_BASE_URL,
    get_headers,
)


ORG_ID = "01b6554c-4884-409f-a0e1-22e394bee989"


async def create_agent_inference_job(client: httpx.AsyncClient, org_id: str, project_id: str) -> str:
    """Creates a cron job for agent inference."""
    job_name = f"Agent Inference Test - Project {project_id}"
    print(f"--- Creating cron job: {job_name} ---")
    payload = {
        "name": job_name,
        "cron_expr": "*/20 * * * * *",  # Every 20 seconds
        "tz": "UTC",
        "entrypoint": "agent_inference",
        "payload": {
            "project_id": project_id,
            "env": "production",
            "input_data": {
                "messages": [
                    {"role": "user", "content": "Hello, how are you ?"},
                ],
            },
        },
    }
    response = await client.post(f"{API_BASE_URL}/crons/{org_id}", json=payload)
    response.raise_for_status()
    job_id = response.json()["id"]
    print(f"✅ Cron job '{job_name}' created with ID: {job_id}")
    return job_id


async def delete_job(client: httpx.AsyncClient, org_id: str, job_id: str, name: str):
    """Deletes a cron job."""
    print(f"--- Deleting cron job: {name} ({job_id}) ---")
    response = await client.delete(f"{API_BASE_URL}/crons/{org_id}/{job_id}")
    response.raise_for_status()
    print(f"✅ Cron job '{name}' deleted successfully.")


async def main():
    """
    Main function to run the agent inference cron job test.
    """
    parser = argparse.ArgumentParser(description="Test agent inference cron jobs.")
    parser.add_argument(
        "--org-id",
        type=UUID,
        required=False,
        help="The organization ID for the test.",
    )
    parser.add_argument(
        "--project-id",
        type=UUID,
        required=True,
        help="The project ID for the agent inference.",
    )
    args = parser.parse_args()

    jwt_token = await authenticate()
    headers = get_headers(jwt_token)
    job_id = None
    job_name = f"Agent Inference Test - Project {args.project_id}"

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        try:
            job_id = await create_agent_inference_job(client, str(args.org_id or ORG_ID), str(args.project_id))

            print("\n" + "=" * 50)
            print("✅ Agent inference job created and scheduled.")
            print("👀 Monitor the FastAPI server logs for execution details.")
            print("Press Ctrl+C to stop and clean up the job...")
            print("=" * 50 + "\n")
            await asyncio.Event().wait()

        except (asyncio.CancelledError, KeyboardInterrupt):
            print("\n🚨 Interruption received. Proceeding to cleanup...")
        except httpx.HTTPStatusError as e:
            print(f"❌ API Error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"❌ An unexpected error occurred: {e}")
        finally:
            if job_id:
                await delete_job(client, str(args.org_id or ORG_ID), job_id, job_name)
            print("✅ Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
