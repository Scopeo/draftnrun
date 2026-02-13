import asyncio
import json
import logging
from typing import Any, Dict
from uuid import UUID

import httpx

from ada_backend.services.webhooks.webhook_service import prepare_workflow_input
from settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Output to stdout for worker to capture
)

LOGGER = logging.getLogger(__name__)

WEBHOOK_WORKFLOW_TIMEOUT = 1800  # 30 minutes in seconds (for long-running workflows)
WEBHOOK_MAX_CONCURRENT_WORKFLOWS = 5  # Maximum number of concurrent workflows to run


async def _run_workflow_async(
    client: httpx.AsyncClient,
    api_base_url: str,
    webhook_api_key: str,
    trigger: Dict[str, Any],
    payload: Dict[str, Any],
    event_id: str,
    provider: str,
    webhook_id: UUID,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool]:
    """
    Run a single workflow asynchronously.

    Returns:
        Tuple of (trigger_id, success: bool)
    """
    trigger_id = trigger["id"]
    project_id = trigger["project_id"]
    async with semaphore:  # Limit concurrent executions
        try:
            LOGGER.info(
                f"[WEBHOOK_MAIN] Triggering workflow/agent for trigger {trigger_id}, "
                f"project_id={project_id}, webhook_id={webhook_id}"
            )

            workflow_input = prepare_workflow_input(payload, provider)

            input_data = {
                **workflow_input,
                "event_id": event_id,
                "provider": provider,
            }

            response = await client.post(
                f"{api_base_url}/internal/webhooks/projects/{project_id}/run",
                json=input_data,
                headers={
                    "X-Webhook-API-Key": webhook_api_key,
                    "Content-Type": "application/json",
                },
                timeout=WEBHOOK_WORKFLOW_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()

            LOGGER.info(
                f"[WEBHOOK_MAIN] Successfully triggered workflow/agent for trigger {trigger_id}: "
                f"trace_id={result.get('trace_id')}"
            )
            return trigger_id, True

        except httpx.HTTPStatusError as e:
            LOGGER.error(
                f"[WEBHOOK_MAIN] HTTP error triggering workflow/agent for trigger {trigger_id}: "
                f"status={e.response.status_code}, error={str(e)}",
                exc_info=True,
            )
            return trigger_id, False
        except httpx.RequestError as e:
            LOGGER.error(
                f"[WEBHOOK_MAIN] Request error triggering workflow/agent for trigger {trigger_id}: {str(e)}",
                exc_info=True,
            )
            return trigger_id, False
        except Exception as e:
            LOGGER.error(
                f"[WEBHOOK_MAIN] Unexpected error triggering workflow/agent for trigger {trigger_id}: {str(e)}",
                exc_info=True,
            )
            return trigger_id, False


async def webhook_main_async(
    webhook_id: UUID,
    provider: str,
    event_id: str,
    organization_id: UUID,
    payload: Dict[str, Any],
):
    LOGGER.info(
        f"[WEBHOOK_MAIN] Starting webhook processing - "
        f"Webhook: {webhook_id}, Provider: {provider}, Event: {event_id}, Org: {organization_id}"
    )

    api_base_url = settings.ADA_URL
    if not api_base_url:
        LOGGER.error("[WEBHOOK_MAIN] ADA_URL not set in environment")
        raise ValueError("ADA_URL environment variable is required")
    webhook_api_key = settings.WEBHOOK_API_KEY
    if not webhook_api_key:
        LOGGER.error("[WEBHOOK_MAIN] WEBHOOK_API_KEY not set in environment")
        raise ValueError("WEBHOOK_API_KEY environment variable is required")

    async with httpx.AsyncClient() as client:
        try:
            triggers_response = await client.get(
                f"{api_base_url}/internal/webhooks/{webhook_id}/triggers",
                params={
                    "provider": provider,
                    "webhook_event_data": json.dumps(payload),
                },
                headers={
                    "X-Webhook-API-Key": webhook_api_key,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            triggers_response.raise_for_status()
            triggers = triggers_response.json()

            if not triggers:
                LOGGER.info(f"[WEBHOOK_MAIN] No enabled triggers found for webhook {webhook_id}, skipping processing")
                return

            LOGGER.info(f"[WEBHOOK_MAIN] Found {len(triggers)} enabled trigger(s) for webhook {webhook_id}")

            max_concurrent = WEBHOOK_MAX_CONCURRENT_WORKFLOWS
            semaphore = asyncio.Semaphore(max_concurrent)
            LOGGER.info(f"[WEBHOOK_MAIN] Limiting concurrent workflows to {max_concurrent}")

            tasks = [
                _run_workflow_async(
                    client=client,
                    api_base_url=api_base_url,
                    webhook_api_key=webhook_api_key,
                    trigger=trigger,
                    payload=payload,
                    event_id=event_id,
                    provider=provider,
                    webhook_id=webhook_id,
                    semaphore=semaphore,
                )
                for trigger in triggers
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed_triggers = sum(1 for result in results if isinstance(result, tuple) and result[1])

            LOGGER.info(
                f"[WEBHOOK_MAIN] Webhook processing completed: webhook_id={webhook_id}, "
                f"event_id={event_id}, processed_triggers={processed_triggers}/{len(triggers)}"
            )

        except httpx.RequestError as e:
            LOGGER.error(f"[WEBHOOK_MAIN] Error calling API: {str(e)}", exc_info=True)
            raise
        except Exception as e:
            LOGGER.error(f"[WEBHOOK_MAIN] Error processing webhook: {str(e)}", exc_info=True)
            raise


def webhook_main(
    webhook_id: str,
    provider: str,
    event_id: str,
    organization_id: str,
    payload: Dict[str, Any],
):
    """
    Entry point for webhook processing script.
    Called by the worker subprocess.

    Args:
        webhook_id: UUID string of the webhook configuration
        provider: Webhook provider name (e.g., 'aircall')
        event_id: Unique event identifier from the webhook payload
        organization_id: UUID string of the organization
        payload: The webhook payload data
    """
    LOGGER.info("[WEBHOOK_MAIN] Entry point called")
    try:
        asyncio.run(
            webhook_main_async(
                webhook_id=UUID(webhook_id),
                provider=provider,
                event_id=event_id,
                organization_id=UUID(organization_id),
                payload=payload,
            )
        )
        LOGGER.info("[WEBHOOK_MAIN] Completed successfully")
    except Exception as e:
        LOGGER.error(f"[WEBHOOK_MAIN] FAILED with error: {str(e)}")
        raise
