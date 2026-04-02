import json
from uuid import uuid4

import pytest
from mixpanel import Consumer

import ada_backend.mixpanel_analytics as mixpanel_analytics


class _VerifyingConsumer(Consumer):
    """Extends the real Consumer: forwards HTTP calls to Mixpanel AND records payloads for assertions."""

    instances: list["_VerifyingConsumer"] = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sent: list[dict] = []
        _VerifyingConsumer.instances.append(self)

    def send(self, endpoint, json_message, api_key=None):
        super().send(endpoint, json_message, api_key)
        self.sent.append({"endpoint": endpoint, "message": json.loads(json_message)})


def _reset():
    mixpanel_analytics._mp = None
    mixpanel_analytics._mp_token = None
    mixpanel_analytics._enabled = False


@pytest.fixture()
def mixpanel_live(monkeypatch):
    token = mixpanel_analytics.settings.MIXPANEL_TOKEN
    if not token:
        pytest.skip("MIXPANEL_TOKEN not configured — skipping live Mixpanel test")

    _VerifyingConsumer.instances.clear()
    monkeypatch.setattr(mixpanel_analytics, "Consumer", _VerifyingConsumer)
    monkeypatch.setattr(mixpanel_analytics.settings, "ENV", "production")
    _reset()
    yield
    _reset()


def _consumer() -> _VerifyingConsumer:
    assert _VerifyingConsumer.instances, "expected at least one _VerifyingConsumer instance"
    return _VerifyingConsumer.instances[0]


def _find_event(consumer: _VerifyingConsumer, endpoint: str, event_name: str | None = None) -> dict:
    for item in consumer.sent:
        if item["endpoint"] != endpoint:
            continue
        if event_name is None or item["message"].get("event") == event_name:
            return item["message"]
    raise AssertionError(f"No {endpoint} message with event={event_name!r} found in {consumer.sent}")


@pytest.mark.mixpanel
class TestMixpanelLiveTracking:

    def test_track_project_saved(self, mixpanel_live):
        user_id, project_id = uuid4(), uuid4()

        mixpanel_analytics.track_project_saved(user_id, project_id)

        msg = _find_event(_consumer(), "events", "Project Saved")
        assert msg["properties"]["distinct_id"] == str(user_id)
        assert msg["properties"]["project_id"] == str(project_id)

    def test_identify_user(self, mixpanel_live):
        user_id, org_id = uuid4(), uuid4()

        mixpanel_analytics.identify_user(user_id, "test@example.com", org_id)

        c = _consumer()
        people_msg = _find_event(c, "people")
        assert people_msg["$distinct_id"] == str(user_id)
        assert people_msg["$set"]["$email"] == "test@example.com"

        track_msg = _find_event(c, "events", "Org Accessed")
        assert track_msg["properties"]["organization_id"] == str(org_id)

    def test_track_run_completed(self, mixpanel_live):
        user_id, project_id, org_id = str(uuid4()), uuid4(), uuid4()

        mixpanel_analytics.track_run_completed(
            user_id=user_id,
            project_id=project_id,
            status="completed",
            trigger="api",
            duration_ms=1234,
            organization_id=org_id,
        )

        msg = _find_event(_consumer(), "events", "Run Completed")
        props = msg["properties"]
        assert props["distinct_id"] == user_id
        assert props["project_id"] == str(project_id)
        assert props["status"] == "completed"
        assert props["trigger"] == "api"
        assert props["duration_ms"] == 1234
        assert props["organization_id"] == str(org_id)

    def test_track_project_created(self, mixpanel_live):
        user_id, org_id, project_id = uuid4(), uuid4(), uuid4()

        mixpanel_analytics.track_project_created(
            user_id=user_id,
            organization_id=org_id,
            project_id=project_id,
            project_name="Test Project",
            project_type="agent",
            from_template=True,
        )

        msg = _find_event(_consumer(), "events", "Project Created")
        props = msg["properties"]
        assert props["project_name"] == "Test Project"
        assert props["project_type"] == "agent"
        assert props["from_template"] is True

    def test_noop_when_not_production(self, monkeypatch):
        token = mixpanel_analytics.settings.MIXPANEL_TOKEN
        if not token:
            pytest.skip("MIXPANEL_TOKEN not configured")

        _VerifyingConsumer.instances.clear()
        monkeypatch.setattr(mixpanel_analytics, "Consumer", _VerifyingConsumer)
        monkeypatch.setattr(mixpanel_analytics.settings, "ENV", "staging")
        _reset()

        try:
            mixpanel_analytics.track_project_saved(uuid4(), uuid4())

            assert mixpanel_analytics._enabled is False
            assert len(_VerifyingConsumer.instances) == 0
        finally:
            _reset()
