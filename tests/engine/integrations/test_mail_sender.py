from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.components.types import ComponentAttributes
from engine.integrations.gmail.gmail_sender import GmailSenderInputs
from engine.integrations.mail_sender import MailSender, MailSenderOutputs


@pytest.fixture
def component_attrs() -> ComponentAttributes:
    return ComponentAttributes(component_instance_name="mail_test", component_instance_id=None)


def test_is_available_gmail_only(component_attrs: ComponentAttributes):
    sender = MailSender(
        MagicMock(),
        component_attrs,
        gmail_access_token="tok",
        outlook_access_token=None,
    )
    assert sender.is_available()


def test_is_available_outlook_only(component_attrs: ComponentAttributes):
    sender = MailSender(
        MagicMock(),
        component_attrs,
        gmail_access_token=None,
        outlook_access_token="tok",
    )
    assert sender.is_available()


def test_is_available_both_disconnected(component_attrs: ComponentAttributes):
    sender = MailSender(MagicMock(), component_attrs)
    assert not sender.is_available()


def test_is_available_both_connected(component_attrs: ComponentAttributes):
    sender = MailSender(
        MagicMock(),
        component_attrs,
        gmail_access_token="g",
        outlook_access_token="o",
    )
    assert not sender.is_available()


@pytest.mark.asyncio
async def test_run_requires_exactly_one_provider(component_attrs: ComponentAttributes):
    sender = MailSender(
        MagicMock(),
        component_attrs,
        gmail_access_token="g",
        outlook_access_token="o",
    )
    with pytest.raises(ValueError, match="only one provider"):
        await sender._run_without_io_trace(GmailSenderInputs(mail_subject="s"), {})


@pytest.mark.asyncio
async def test_run_requires_any_provider(component_attrs: ComponentAttributes):
    sender = MailSender(MagicMock(), component_attrs)
    with pytest.raises(ValueError, match="Gmail or Outlook"):
        await sender._run_without_io_trace(GmailSenderInputs(mail_subject="s"), {})


@pytest.mark.asyncio
async def test_delegates_to_gmail(component_attrs: ComponentAttributes):
    with patch("engine.integrations.mail_sender.GmailSenderV2") as mock_cls:
        inner = mock_cls.return_value
        inner._run_without_io_trace = AsyncMock(
            return_value=MailSenderOutputs(status="sent", message_id="mid-g")
        )
        sender = MailSender(
            MagicMock(),
            component_attrs,
            gmail_access_token="g",
        )
        out = await sender._run_without_io_trace(GmailSenderInputs(mail_subject="sub"), {})
        assert out.status == "sent"
        assert out.message_id == "mid-g"
        mock_cls.assert_called_once()


@pytest.mark.asyncio
async def test_delegates_to_outlook(component_attrs: ComponentAttributes):
    with patch("engine.integrations.mail_sender.OutlookSender") as mock_cls:
        inner = mock_cls.return_value
        inner._run_without_io_trace = AsyncMock(
            return_value=MailSenderOutputs(status="sent", message_id=None)
        )
        sender = MailSender(
            MagicMock(),
            component_attrs,
            outlook_access_token="o",
        )
        out = await sender._run_without_io_trace(GmailSenderInputs(mail_subject="sub"), {})
        assert out.status == "sent"
        assert out.message_id is None
        mock_cls.assert_called_once()
