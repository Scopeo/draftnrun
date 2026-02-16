import asyncio
import logging
from typing import Any, Dict
from uuid import UUID

import httpx

from settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Output to stdout for worker to capture
)

LOGGER = logging.getLogger(__name__)

WEBHOOK_EXECUTE_TIMEOUT = 1860  # Slightly above 30 min to allow for long-running workflows


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

    body = {
        "provider": provider,
        "event_id": event_id,
        "organization_id": str(organization_id),
        "payload": payload,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{api_base_url}/internal/webhooks/{webhook_id}/execute",
                json=body,
                headers={
                    "X-Webhook-API-Key": webhook_api_key,
                    "Content-Type": "application/json",
                },
                timeout=WEBHOOK_EXECUTE_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()

        processed = result.get("processed", 0)
        total = result.get("total", 0)
        LOGGER.info(
            f"[WEBHOOK_MAIN] Webhook processing completed: webhook_id={webhook_id}, "
            f"event_id={event_id}, processed_triggers={processed}/{total}"
        )
    except httpx.HTTPStatusError as e:
        LOGGER.error(
            f"[WEBHOOK_MAIN] HTTP error calling execute: status={e.response.status_code}, error={str(e)}",
            exc_info=True,
        )
        raise
    except httpx.RequestError as e:
        LOGGER.error(f"[WEBHOOK_MAIN] Request error calling execute: {str(e)}", exc_info=True)
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
