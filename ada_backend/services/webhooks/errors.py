from typing import Any, Dict

from ada_backend.database.models import Webhook, WebhookProvider


class WebhookServiceError(Exception):
    """Base exception for webhook service errors."""

    code = "webhook_service_error"


class WebhookEmptyTokenError(WebhookServiceError):
    """Raised when a webhook token is empty."""

    def __init__(self, provider: WebhookProvider):
        self.provider = provider
        super().__init__(f"Webhook token is empty for provider: {provider}")


class WebhookNotFoundError(WebhookServiceError):
    """Raised when a webhook is not found."""

    def __init__(self, provider: WebhookProvider, external_client_id: str):
        self.provider = provider
        self.external_client_id = external_client_id
        super().__init__(
            f"Webhook not found for provider: {provider} and external "
            f"client id starts with: {external_client_id[:4]}..."
        )


class WebhookProcessingError(WebhookServiceError):
    """Raised when there is an error processing a webhook."""

    def __init__(self, webhook: Webhook, error: Exception):
        self.webhook = webhook
        self.error = error
        super().__init__(f"Error processing webhook {webhook.id}: {str(error)}")


class WebhookEventIdNotFoundError(WebhookServiceError):
    """Raised when a webhook event id is not found."""

    def __init__(self, provider: WebhookProvider, payload: Dict[str, Any]):
        self.provider = provider
        self.payload = payload
        payload_keys = list(payload.keys()) if isinstance(payload, dict) else "N/A"
        super().__init__(
            f"Webhook event id not found for provider: {provider}. Payload structure keys: {payload_keys}"
        )


class WebhookQueueError(WebhookServiceError):
    """Raised when a webhook event fails to be queued in Redis."""

    def __init__(self, webhook: Webhook, event_id: str, reason: str = "Failed to queue webhook event to Redis"):
        self.webhook = webhook
        self.event_id = event_id
        self.reason = reason
        super().__init__(
            f"Failed to queue webhook event {event_id} for webhook {webhook.id} "
            f"(provider: {webhook.provider}): {reason}"
        )


class WebhookSignatureVerificationError(WebhookServiceError):
    """Raised when Svix signature verification fails."""

    def __init__(self, message: str = "Invalid Svix signature"):
        self.message = message
        super().__init__(self.message)


class WebhookConfigurationError(WebhookServiceError):
    """Raised when webhook configuration is invalid or missing."""

    def __init__(self, provider: WebhookProvider, message: str):
        self.provider = provider
        super().__init__(f"Configuration error for {provider}: {message}")


class WebhookInvalidParameterError(WebhookServiceError):
    """Raised when a webhook parameter is invalid."""

    def __init__(self, parameter: str, value: str, reason: str):
        self.parameter = parameter
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid parameter '{parameter}' with value '{value}': {reason}")
