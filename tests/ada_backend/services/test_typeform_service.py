import base64
import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import IntegrationTrigger, Webhook, WebhookProvider
from ada_backend.services.webhooks.errors import (
    WebhookConfigurationError,
    WebhookEventIdNotFoundError,
    WebhookSignatureVerificationError,
)
from ada_backend.services.webhooks.typeform_service import get_typeform_event_id, verify_typeform_signature
from ada_backend.services.webhooks.typeform_setup_service import (
    _build_typeform_callback_url,
    create_typeform_webhook_service,
)


def _typeform_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return "sha256=" + base64.b64encode(digest).decode()


def test_verify_typeform_signature_accepts_valid_signature():
    secret = "typeform-secret"
    body = b'{"event_id":"evt-1"}'

    verify_typeform_signature(
        {"typeform-signature": _typeform_signature(secret, body)},
        body,
        secret,
    )


def test_verify_typeform_signature_rejects_invalid_signature():
    with pytest.raises(WebhookSignatureVerificationError):
        verify_typeform_signature(
            {"typeform-signature": "sha256=invalid"},
            b'{"event_id":"evt-1"}',
            "typeform-secret",
        )


def test_verify_typeform_signature_requires_header():
    with pytest.raises(WebhookSignatureVerificationError):
        verify_typeform_signature({}, b"{}", "typeform-secret")


def test_verify_typeform_signature_rejects_malformed_header():
    with pytest.raises(WebhookSignatureVerificationError):
        verify_typeform_signature({"typeform-signature": "not-a-signature"}, b"{}", "typeform-secret")


def test_get_typeform_event_id_uses_event_id():
    assert get_typeform_event_id({"event_id": "evt-1", "form_response": {"token": "token-1"}}) == "evt-1"


def test_get_typeform_event_id_falls_back_to_response_token():
    assert get_typeform_event_id({"form_response": {"token": "token-1"}}) == "token-1"


def test_get_typeform_event_id_raises_when_missing():
    with pytest.raises(WebhookEventIdNotFoundError):
        get_typeform_event_id({"form_response": {}})


def test_create_typeform_webhook_creates_encrypted_secret_and_trigger():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    webhook_id = uuid4()
    trigger_id = uuid4()
    added = []

    def add_side_effect(item):
        added.append(item)

    def flush_side_effect():
        for item in added:
            if isinstance(item, Webhook) and item.id is None:
                item.id = webhook_id
            if isinstance(item, IntegrationTrigger) and item.id is None:
                item.id = trigger_id

    session.add.side_effect = add_side_effect
    session.flush.side_effect = flush_side_effect

    with (
        patch("ada_backend.services.webhooks.typeform_setup_service.get_project") as get_project_mock,
        patch(
            "ada_backend.services.webhooks.typeform_setup_service._get_typeform_webhook_for_project", return_value=None
        ),
        patch("ada_backend.services.webhooks.typeform_setup_service._get_typeform_trigger", return_value=None),
        patch(
            "ada_backend.services.webhooks.typeform_setup_service._generate_signing_secret",
            return_value="created-secret",
        ),
        patch("ada_backend.services.webhooks.typeform_setup_service.settings.ADA_URL", "https://ada.example.test/"),
    ):
        get_project_mock.return_value = SimpleNamespace(id=project_id, organization_id=organization_id)
        response = create_typeform_webhook_service(session=session, project_id=project_id)

    created_webhook = next(item for item in added if isinstance(item, Webhook))
    created_trigger = next(item for item in added if isinstance(item, IntegrationTrigger))

    assert created_webhook.provider == WebhookProvider.TYPEFORM
    assert created_webhook.external_client_id == f"typeform:{project_id}"
    assert created_webhook.encrypted_signing_secret is not None
    assert created_webhook.get_signing_secret() == "created-secret"
    assert created_trigger.webhook_id == webhook_id
    assert created_trigger.project_id == project_id
    assert response.webhook_id == webhook_id
    assert response.integration_trigger_id == trigger_id
    assert response.callback_url == f"https://ada.example.test/webhooks/typeform/{webhook_id}"
    assert response.signing_secret == "created-secret"
    assert response.secret_available is True
    session.commit.assert_called_once()


def test_create_typeform_webhook_reuses_existing_without_returning_secret():
    session = MagicMock()
    project_id = uuid4()
    webhook = Webhook(
        id=uuid4(),
        organization_id=uuid4(),
        provider=WebhookProvider.TYPEFORM,
        external_client_id=f"typeform:{project_id}",
    )
    webhook.set_signing_secret("existing-secret")
    trigger = IntegrationTrigger(
        id=uuid4(),
        webhook_id=webhook.id,
        project_id=project_id,
        events_hash="events-hash",
        enabled=True,
    )

    with (
        patch("ada_backend.services.webhooks.typeform_setup_service.get_project") as get_project_mock,
        patch(
            "ada_backend.services.webhooks.typeform_setup_service._get_typeform_webhook_for_project",
            return_value=webhook,
        ),
        patch("ada_backend.services.webhooks.typeform_setup_service._get_typeform_trigger", return_value=trigger),
        patch("ada_backend.services.webhooks.typeform_setup_service.settings.ADA_URL", "https://ada.example.test"),
    ):
        get_project_mock.return_value = SimpleNamespace(id=project_id, organization_id=webhook.organization_id)
        response = create_typeform_webhook_service(session=session, project_id=project_id)

    assert response.webhook_id == webhook.id
    assert response.integration_trigger_id == trigger.id
    assert response.callback_url == f"https://ada.example.test/webhooks/typeform/{webhook.id}"
    assert response.signing_secret is None
    assert response.secret_available is False
    assert webhook.get_signing_secret() == "existing-secret"
    session.add.assert_not_called()


def test_build_typeform_callback_url_requires_ada_url():
    with (
        patch("ada_backend.services.webhooks.typeform_setup_service.settings.ADA_URL", None),
        pytest.raises(WebhookConfigurationError, match="ADA_URL is not configured"),
    ):
        _build_typeform_callback_url(uuid4())
