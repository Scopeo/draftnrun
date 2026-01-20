import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.models import WebhookProvider
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.webhook_schema import WebhookProcessingStatus
from ada_backend.services.webhooks.aircall_service import (
    get_aircall_webhook_service,
)
from ada_backend.services.webhooks.errors import WebhookEmptyTokenError, WebhookNotFoundError, WebhookQueueError
from ada_backend.services.webhooks.webhook_service import process_webhook_event

router = APIRouter(tags=["Webhooks"])

LOGGER = logging.getLogger(__name__)


@router.post("/webhooks/aircall")
async def receive_aircall_webhook(
    payload: Dict[str, Any] = Body(...),
    session: Session = Depends(get_db),
):
    try:
        webhook = get_aircall_webhook_service(session, payload.get("token"))
        result = await process_webhook_event(
            provider=WebhookProvider.AIRCALL,
            payload=payload,
            webhook=webhook,
        )

        if result.status not in [
            WebhookProcessingStatus.DUPLICATE,
            WebhookProcessingStatus.RECEIVED,
        ]:
            error_message = "Failed to process Aircall webhook"
            LOGGER.error(f"Failed to process Aircall webhook: {result.status}", exc_info=True)
            raise HTTPException(status_code=400, detail=error_message)
        return {"status": "ok"}
    except WebhookEmptyTokenError as e:
        LOGGER.error(f"Error processing Aircall webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Missing Aircall token")
    except WebhookNotFoundError as e:
        LOGGER.error(f"Error processing Aircall webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid Aircall token")
    except WebhookQueueError as e:
        LOGGER.error(f"Error processing Aircall webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to queue Aircall webhook")
    except Exception as e:
        LOGGER.error(f"Error processing Aircall webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
