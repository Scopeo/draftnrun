import asyncio
import logging
import os
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Output to stdout for worker to capture
)

LOGGER = logging.getLogger(__name__)

WEBHOOK_EXECUTE_TIMEOUT = 1860  # Slightly above 30 min to allow for long-running workflows


DIRECT_TRIGGER_PROVIDER = "direct_trigger"


async def _post(url: str, body: Dict[str, Any], webhook_api_key: str, context: str) -> Dict[str, Any]:
    """POST to an internal endpoint with shared auth headers and error handling.

    Args:
        url: Full URL to POST to.
        body: JSON-serialisable request body.
        webhook_api_key: Value for the X-Webhook-API-Key header.
        context: Short label used in log messages to identify the call site.

    Returns:
        Parsed JSON response body.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=body,
                headers={
                    "X-Webhook-API-Key": webhook_api_key,
                    "Content-Type": "application/json",
                },
                timeout=WEBHOOK_EXECUTE_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        LOGGER.error(
            f"[WEBHOOK_MAIN] HTTP error on {context}: status={e.response.status_code}, error={str(e)}",
            exc_info=True,
        )
        raise
    except httpx.RequestError as e:
        LOGGER.error(f"[WEBHOOK_MAIN] Request error on {context}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        LOGGER.error(f"[WEBHOOK_MAIN] Error on {context}: {str(e)}", exc_info=True)
        raise


async def webhook_main_async(
    webhook_id: UUID,
    provider: str,
    event_id: str,
    payload: Dict[str, Any],
    organization_id: Optional[UUID] = None,
):
    LOGGER.info(
        f"[WEBHOOK_MAIN] Starting webhook processing - "
        f"Webhook: {webhook_id}, Provider: {provider}, Event: {event_id}, "
        f"Org: {organization_id if organization_id else 'None'}"
    )

    api_base_url = os.environ.get("ADA_URL")
    if not api_base_url:
        LOGGER.error("[WEBHOOK_MAIN] ADA_URL not set in environment")
        raise ValueError("ADA_URL environment variable is required")
    webhook_api_key = os.environ.get("WEBHOOK_API_KEY")
    if not webhook_api_key:
        LOGGER.error("[WEBHOOK_MAIN] WEBHOOK_API_KEY not set in environment")
        raise ValueError("WEBHOOK_API_KEY environment variable is required")

    if provider == DIRECT_TRIGGER_PROVIDER:
        await _run_direct_trigger(
            project_id=webhook_id,
            payload=payload,
            event_id=event_id,
            api_base_url=api_base_url,
            webhook_api_key=webhook_api_key,
        )
        return

    body = {
        "provider": provider,
        "event_id": event_id,
        "organization_id": str(organization_id) if organization_id else None,
        "payload": payload,
    }

    result = await _post(
        url=f"{api_base_url}/internal/webhooks/{webhook_id}/execute",
        body=body,
        webhook_api_key=webhook_api_key,
        context="webhook execute",
    )
    processed = result.get("processed", 0)
    total = result.get("total", 0)
    LOGGER.info(
        f"[WEBHOOK_MAIN] Webhook processing completed: webhook_id={webhook_id}, "
        f"event_id={event_id}, processed_triggers={processed}/{total}"
    )


async def _run_direct_trigger(
    project_id: UUID,
    payload: Dict[str, Any],
    event_id: str,
    api_base_url: str,
    webhook_api_key: str,
) -> None:
    """Call the internal direct-trigger run endpoint for a specific project and env."""
    env = payload.pop("env", None)
    if not env:
        raise ValueError("Missing 'env' in direct trigger payload")
    LOGGER.info(f"[WEBHOOK_MAIN] Direct trigger: project_id={project_id}, env={env}, event_id={event_id}")

    await _post(
        url=f"{api_base_url}/internal/webhooks/projects/{project_id}/envs/{env}/run",
        body=payload,
        webhook_api_key=webhook_api_key,
        context="direct trigger",
    )
    LOGGER.info(f"[WEBHOOK_MAIN] Direct trigger completed: project_id={project_id}, env={env}, event_id={event_id}")


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
                organization_id=UUID(organization_id) if organization_id else None,
                payload=payload,
            )
        )
        LOGGER.info("[WEBHOOK_MAIN] Completed successfully")
    except Exception as e:
        LOGGER.error(f"[WEBHOOK_MAIN] FAILED with error: {str(e)}")
        raise
