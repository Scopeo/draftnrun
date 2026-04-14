from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, alert_emails
from tests.mcp_server.conftest import FAKE_PROJECT_ID

FAKE_ALERT_EMAIL_ID = "00000000-0000-4000-8000-0000000000f1"


@pytest.mark.asyncio
async def test_list_alert_emails(monkeypatch, fake_mcp):
    mcp = fake_mcp
    get_mock = AsyncMock(return_value=[{"id": FAKE_ALERT_EMAIL_ID, "email": "dev@test.com"}])

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory.api, "get", get_mock)

    alert_emails.register(mcp)

    result = await mcp.tools["list_alert_emails"](FAKE_PROJECT_ID)

    assert result == [{"id": FAKE_ALERT_EMAIL_ID, "email": "dev@test.com"}]
    get_mock.assert_awaited_once_with(
        f"/projects/{FAKE_PROJECT_ID}/alert-emails",
        "jwt-token",
        trim=True,
    )


@pytest.mark.asyncio
async def test_create_alert_email(monkeypatch, fake_mcp):
    mcp = fake_mcp
    role_mock = AsyncMock(return_value={"org_id": "org-123"})
    post_mock = AsyncMock(return_value={"id": FAKE_ALERT_EMAIL_ID, "email": "dev@test.com"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "post", post_mock)

    alert_emails.register(mcp)

    result = await mcp.tools["create_alert_email"](FAKE_PROJECT_ID, "dev@test.com")

    assert result == {"id": FAKE_ALERT_EMAIL_ID, "email": "dev@test.com"}
    role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
    post_mock.assert_awaited_once_with(
        f"/projects/{FAKE_PROJECT_ID}/alert-emails",
        "jwt-token",
        trim=True,
        json={"email": "dev@test.com"},
    )


@pytest.mark.asyncio
async def test_delete_alert_email(monkeypatch, fake_mcp):
    mcp = fake_mcp
    role_mock = AsyncMock(return_value={"org_id": "org-123"})
    delete_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "delete", delete_mock)

    alert_emails.register(mcp)

    result = await mcp.tools["delete_alert_email"](FAKE_PROJECT_ID, FAKE_ALERT_EMAIL_ID)

    assert result == {"status": "ok"}
    role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
    delete_mock.assert_awaited_once_with(
        f"/projects/{FAKE_PROJECT_ID}/alert-emails/{FAKE_ALERT_EMAIL_ID}",
        "jwt-token",
        trim=True,
    )
