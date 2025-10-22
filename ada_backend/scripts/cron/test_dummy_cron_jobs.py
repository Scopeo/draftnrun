import argparse
import asyncio
import httpx


from ada_backend.scripts.cron.test_cron_crud import (
    authenticate,
    API_BASE_URL,
    get_headers,
)

# --- Script Configuration ---
ORG_ID = "01b6554c-4884-409f-a0e1-22e394bee989"


async def create_dummy_job(
    client: httpx.AsyncClient,
    org_id: str,
    name: str,
    cron_expr: str,
    message: str,
    payload: dict = None,
) -> str:
    """Creates a cron job using the dummy_print entrypoint."""
    print(f"--- Creating cron job: {name} ---")

    # If no custom payload is provided, create a default one
    if payload is None:
        payload = {"message": message}

    request_payload = {
        "name": name,
        "cron_expr": cron_expr,
        "tz": "UTC",
        "entrypoint": "dummy_print",
        "payload": payload,
    }
    response = await client.post(f"{API_BASE_URL}/organizations/{org_id}/crons", json=request_payload)
    response.raise_for_status()
    job_id = response.json()["id"]
    print(f"✅ Cron job '{name}' created with ID: {job_id}")
    return job_id


async def delete_job(client: httpx.AsyncClient, org_id: str, job_id: str, name: str):
    """Deletes a cron job."""
    print(f"--- Deleting cron job: {name} ({job_id}) ---")
    response = await client.delete(f"{API_BASE_URL}/organizations/{org_id}/crons/{job_id}")
    response.raise_for_status()
    print(f"✅ Cron job '{name}' deleted successfully.")


async def main():
    """
    Main function to run the dummy cron job test.
    1. Authenticates.
    2. Creates two dummy cron jobs with different schedules.
    3. Waits for user interruption (Ctrl+C).
    4. Deletes the cron jobs upon interruption.
    """
    parser = argparse.ArgumentParser(description="Test dummy cron jobs.")
    parser.add_argument(
        "--org-id",
        type=str,
        required=False,
        help="The organization ID to use for the test.",
    )
    args = parser.parse_args()
    org_id = args.org_id or ORG_ID

    # 1. Authenticate
    jwt_token = await authenticate()
    headers = get_headers(jwt_token)

    job1_id = None
    job2_id = None

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        try:
            # 2. Create jobs
            job1_id = await create_dummy_job(
                client,
                org_id,
                name="Dummy Job 1 (Every 10s)",
                cron_expr="*/10 * * * * *",  # APScheduler extended format for seconds
                message="Hello from Dummy Job 1!",
            )
            job2_id = await create_dummy_job(
                client,
                org_id,
                name="Dummy Job 2 (Every 15s, 50% errors)",
                cron_expr="*/15 * * * * *",
                message="Hello from Dummy Job 2!",
                payload={"message": "Hello from Dummy Job 2!", "error_rate": 0.5},
            )

            # 3. Wait and Observe
            print("\n" + "=" * 50)
            print("✅ Jobs created. The scheduler is now running them.")
            print("👀 Please check the FastAPI server logs for the print statements.")
            print("Press Ctrl+C to stop and clean up...")
            print("=" * 50 + "\n")

            # Wait indefinitely until interrupted
            await asyncio.Event().wait()

        except asyncio.CancelledError:
            print("\n🚨 Interruption received. Proceeding to cleanup...")
        except httpx.HTTPStatusError as e:
            print(f"❌ API Error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"❌ An unexpected error occurred: {e}")
        finally:
            # 4. Cleanup
            print("\n--- Starting Cleanup ---")
            if job1_id:
                await delete_job(client, org_id, job1_id, "Dummy Job 1")
            if job2_id:
                await delete_job(client, org_id, job2_id, "Dummy Job 2")
            print("✅ Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
