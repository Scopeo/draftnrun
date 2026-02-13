import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ada_backend.database.models import WebhookProvider
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.webhook_schema import WebhookProcessingStatus
from ada_backend.services.webhooks.aircall_service import get_aircall_webhook_service
from ada_backend.services.webhooks.errors import (
    WebhookEmptyTokenError,
    WebhookNotFoundError,
    WebhookQueueError,
    WebhookSignatureVerificationError,
)
from ada_backend.services.webhooks.resend_service import (
    get_resend_webhook_service,
    verify_svix_signature,
)
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


@router.post("/webhooks/resend")
async def receive_resend_webhook(
    request: Request,
    session: Session = Depends(get_db),
):
    try:
        raw_body = await request.body()
        payload = await request.json()

        webhook = get_resend_webhook_service(session)

        headers_dict = dict(request.headers)
        verify_svix_signature(headers_dict, raw_body, webhook.external_client_id)

        result = await process_webhook_event(
            provider=WebhookProvider.RESEND,
            payload=payload,
            webhook=webhook,
        )

        if result.status not in [
            WebhookProcessingStatus.DUPLICATE,
            WebhookProcessingStatus.RECEIVED,
        ]:
            error_message = "Failed to process Resend webhook"
            LOGGER.error(f"Failed to process Resend webhook: {result.status}", exc_info=True)
            raise HTTPException(status_code=400, detail=error_message)
        return {"status": "ok"}
    except WebhookSignatureVerificationError as e:
        LOGGER.error(f"Error processing Resend webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    except WebhookNotFoundError as e:
        LOGGER.error(f"Error processing Resend webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail="No Resend webhook configured")
    except WebhookQueueError as e:
        LOGGER.error(f"Error processing Resend webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to queue Resend webhook")
    except Exception as e:
        LOGGER.error(f"Error processing Resend webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
