import logging

import httpx

from settings import settings

LOGGER = logging.getLogger(__name__)

RESEND_SEND_URL = "https://api.resend.com/emails"


def send_email(to: list[str], subject: str, html: str) -> None:
    if not settings.RESEND_API_KEY or not settings.RESEND_FROM_EMAIL:
        LOGGER.warning("Resend not configured (RESEND_API_KEY or RESEND_FROM_EMAIL missing), skipping email")
        return

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                RESEND_SEND_URL,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.RESEND_FROM_EMAIL,
                    "to": to,
                    "subject": subject,
                    "html": html,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError:
        LOGGER.exception("Resend API returned an error while sending alert email")
    except httpx.RequestError:
        LOGGER.exception("Network error while sending alert email via Resend")
    except Exception:
        LOGGER.exception("Unexpected error while sending alert email")
