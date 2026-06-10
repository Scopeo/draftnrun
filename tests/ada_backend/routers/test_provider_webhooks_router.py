import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from ada_backend.database.models import Webhook, WebhookProvider
from ada_backend.routers.webhooks.provider_webhooks_router import receive_resend_webhook, receive_typeform_webhook
from ada_backend.schemas.webhook_schema import WebhookProcessingResponseSchema, WebhookProcessingStatus
from ada_backend.services.webhooks.errors import WebhookNotFoundError, WebhookSignatureVerificationError


def _request(body: bytes, headers: dict[str, str]) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhooks/typeform/test",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        },
        receive,
    )


def _typeform_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return "sha256=" + base64.b64encode(digest).decode()


def _invalid_svix_headers() -> dict[str, str]:
    return {
        "svix-id": "msg_1",
        "svix-timestamp": "123",
        "svix-signature": "invalid",
    }


@pytest.mark.asyncio
async def test_receive_resend_webhook_rejects_invalid_signature_before_parsing_json():
    webhook = Webhook(
        id=uuid4(),
        organization_id=uuid4(),
        provider=WebhookProvider.RESEND,
        external_client_id="resend-secret",
    )

    with (
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.get_resend_webhook_service",
            return_value=webhook,
        ),
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.process_webhook_event",
            new=AsyncMock(),
        ) as process_mock,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await receive_resend_webhook(
                request=_request(b'{"id":', _invalid_svix_headers()),
                session=MagicMock(),
            )

    assert exc_info.value.status_code == 401
    process_mock.assert_not_called()


@pytest.mark.asyncio
async def test_receive_typeform_webhook_verifies_and_queues():
    webhook_id = uuid4()
    secret = "typeform-secret"
    payload = {"event_id": "evt-1", "form_response": {"token": "token-1"}}
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    webhook = Webhook(
        id=webhook_id,
        organization_id=uuid4(),
        provider=WebhookProvider.TYPEFORM,
        external_client_id=f"typeform:{webhook_id}",
    )
    webhook.set_signing_secret(secret)

    with (
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.get_typeform_webhook_service",
            return_value=webhook,
        ),
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.process_webhook_event",
            new=AsyncMock(
                return_value=WebhookProcessingResponseSchema(
                    status=WebhookProcessingStatus.RECEIVED,
                    processed=False,
                    event_id="evt-1",
                )
            ),
        ) as process_mock,
    ):
        response = await receive_typeform_webhook(
            webhook_id=webhook_id,
            request=_request(raw_body, {"Typeform-Signature": _typeform_signature(secret, raw_body)}),
            session=MagicMock(),
        )

    assert response == {"status": "ok"}
    process_mock.assert_awaited_once_with(
        provider=WebhookProvider.TYPEFORM,
        payload=payload,
        webhook=webhook,
    )


@pytest.mark.asyncio
async def test_receive_typeform_webhook_rejects_invalid_signature_before_queueing():
    webhook_id = uuid4()
    webhook = Webhook(
        id=webhook_id,
        organization_id=uuid4(),
        provider=WebhookProvider.TYPEFORM,
        external_client_id=f"typeform:{webhook_id}",
    )
    webhook.set_signing_secret("typeform-secret")

    with (
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.get_typeform_webhook_service",
            return_value=webhook,
        ),
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.process_webhook_event",
            new=AsyncMock(),
        ) as process_mock,
    ):
        with pytest.raises(WebhookSignatureVerificationError) as exc_info:
            await receive_typeform_webhook(
                webhook_id=webhook_id,
                request=_request(b'{"event_id":"evt-1"}', {"Typeform-Signature": "sha256=invalid"}),
                session=MagicMock(),
            )

    assert exc_info.value.status_code == 401
    process_mock.assert_not_called()


@pytest.mark.asyncio
async def test_receive_typeform_webhook_rejects_invalid_signature_before_parsing_json():
    webhook_id = uuid4()
    webhook = Webhook(
        id=webhook_id,
        organization_id=uuid4(),
        provider=WebhookProvider.TYPEFORM,
        external_client_id=f"typeform:{webhook_id}",
    )
    webhook.set_signing_secret("typeform-secret")

    with (
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.get_typeform_webhook_service",
            return_value=webhook,
        ),
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.process_webhook_event",
            new=AsyncMock(),
        ) as process_mock,
    ):
        with pytest.raises(WebhookSignatureVerificationError) as exc_info:
            await receive_typeform_webhook(
                webhook_id=webhook_id,
                request=_request(b'{"event_id":', {"Typeform-Signature": "sha256=invalid"}),
                session=MagicMock(),
            )

    assert exc_info.value.status_code == 401
    process_mock.assert_not_called()


@pytest.mark.asyncio
async def test_receive_typeform_webhook_propagates_service_errors():
    webhook_id = uuid4()

    with (
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.get_typeform_webhook_service",
            side_effect=WebhookNotFoundError(provider=WebhookProvider.TYPEFORM, external_client_id=str(webhook_id)),
        ),
        patch(
            "ada_backend.routers.webhooks.provider_webhooks_router.process_webhook_event",
            new=AsyncMock(),
        ) as process_mock,
    ):
        with pytest.raises(WebhookNotFoundError) as exc_info:
            await receive_typeform_webhook(
                webhook_id=webhook_id,
                request=_request(b'{"event_id":"evt-1"}', {"Typeform-Signature": "sha256=invalid"}),
                session=MagicMock(),
            )

    assert exc_info.value.status_code == 404
    process_mock.assert_not_called()
