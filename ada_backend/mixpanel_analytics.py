import functools
import logging
import threading
from typing import Optional
from uuid import UUID

from mixpanel import Consumer, Mixpanel

from settings import settings

LOGGER = logging.getLogger(__name__)

_mp: Mixpanel | None = None
_mp_token: str | None = None
_enabled: bool = False
_init_lock = threading.Lock()


def _is_production_env() -> bool:
    env = (settings.ENV or "").strip().lower()
    return env == "production"


def _refresh_client() -> None:
    """Initialize (or reinitialize) the Mixpanel client based on current runtime settings."""
    global _mp, _mp_token, _enabled

    token = settings.MIXPANEL_TOKEN
    if token and _is_production_env() and _enabled and _mp is not None and _mp_token == token:
        return

    with _init_lock:
        token = settings.MIXPANEL_TOKEN
        if not token or not _is_production_env():
            _mp = None
            _mp_token = None
            _enabled = False
            return

        if _enabled and _mp is not None and _mp_token == token:
            return

        try:
            _mp = Mixpanel(token, consumer=Consumer(request_timeout=5))
            _mp_token = token
            _enabled = True
        except Exception:
            LOGGER.exception("Mixpanel initialization failed")
            _mp = None
            _mp_token = None
            _enabled = False


def non_breaking_track(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        _refresh_client()
        if not _enabled:
            return
        try:
            return func(*args, **kwargs)
        except Exception as e:
            LOGGER.warning(f"Mixpanel tracking failed in {func.__name__}: {e}")
            return None

    return wrapper


def _str(val) -> str:
    return str(val) if val is not None else ""


def _base_props(organization_id: UUID | None = None) -> dict:
    props = {}
    if settings.ENV:
        props["env"] = settings.ENV
    if organization_id:
        props["organization_id"] = _str(organization_id)
    return props


# ── Identity ──────────────────────────────────────────────────────────────────


@non_breaking_track
def identify_user(user_id: UUID, user_email: str, organization_id: UUID):
    _mp.people_set(_str(user_id), {"$email": user_email, "last_organization_id": _str(organization_id)})
    _mp.track(_str(user_id), "Org Accessed", {**_base_props(organization_id)})


# ── Projects & Agents ─────────────────────────────────────────────────────────


@non_breaking_track
def track_project_created(
    user_id: UUID,
    organization_id: UUID,
    project_id: UUID,
    project_name: str,
    project_type: str = "workflow",
    from_template: bool = False,
):
    _mp.track(
        _str(user_id),
        "Project Created",
        {
            **_base_props(organization_id),
            "project_id": _str(project_id),
            "project_name": project_name,
            "project_type": project_type,
            "from_template": from_template,
        },
    )


@non_breaking_track
def track_project_saved(user_id: UUID, project_id: UUID):
    _mp.track(_str(user_id), "Project Saved", {**_base_props(), "project_id": _str(project_id)})


@non_breaking_track
def track_agent_created(
    user_id: UUID,
    organization_id: UUID,
    agent_id: UUID,
    agent_name: str,
    from_template: bool = False,
):
    _mp.track(
        _str(user_id),
        "Agent Created",
        {
            **_base_props(organization_id),
            "agent_id": _str(agent_id),
            "agent_name": agent_name,
            "from_template": from_template,
        },
    )


# ── Graph / Deployment ────────────────────────────────────────────────────────


@non_breaking_track
def track_deployed_to_production(user_id: UUID, organization_id: UUID, project_id: UUID):
    _mp.track(
        _str(user_id),
        "Deployed to Production",
        {**_base_props(organization_id), "project_id": _str(project_id)},
    )


@non_breaking_track
def track_version_tagged(user_id: UUID, organization_id: UUID, project_id: UUID):
    _mp.track(
        _str(user_id),
        "Version Tagged",
        {**_base_props(organization_id), "project_id": _str(project_id)},
    )


# ── Runs / Execution ─────────────────────────────────────────────────────────


@non_breaking_track
def track_run_completed(
    user_id: str | None,
    project_id: UUID,
    status: str,
    trigger: str,
    duration_ms: int | None = None,
    organization_id: UUID | None = None,
):
    distinct_id = user_id.strip() if user_id and user_id.strip() else _str(project_id)
    _mp.track(
        distinct_id,
        "Run Completed",
        {
            **_base_props(organization_id),
            "project_id": _str(project_id),
            "status": status,
            "trigger": trigger,
            "duration_ms": duration_ms,
        },
    )


# ── Knowledge / Ingestion ────────────────────────────────────────────────────


@non_breaking_track
def track_knowledge_source_created(user_id: UUID, organization_id: UUID, source_type: str):
    _mp.track(
        _str(user_id),
        "Knowledge Source Created",
        {**_base_props(organization_id), "source_type": source_type},
    )


@non_breaking_track
def track_ingestion_task_created(
    task_id: UUID,
    organization_id: UUID,
    source_type: str,
    user_id: UUID | None = None,
    api_key_id: UUID | None = None,
):
    distinct_id = _str(user_id) if user_id else _str(organization_id)
    props = {
        **_base_props(organization_id),
        "task_id": _str(task_id),
        "source_type": source_type,
        "triggered_by": "api_key" if api_key_id else "user",
    }
    if api_key_id:
        props["api_key_id"] = _str(api_key_id)
    _mp.track(distinct_id, "Ingestion Task Created", props)


# ── Scheduling ────────────────────────────────────────────────────────────────


@non_breaking_track
def track_cron_job_created(user_id: UUID, organization_id: UUID, entrypoint: str):
    _mp.track(
        _str(user_id),
        "Cron Job Created",
        {**_base_props(organization_id), "entrypoint": entrypoint},
    )


@non_breaking_track
def track_cron_job_deleted(user_id: UUID, organization_id: UUID):
    _mp.track(_str(user_id), "Cron Job Deleted", {**_base_props(organization_id)})


@non_breaking_track
def track_cron_job_toggled(user_id: UUID, organization_id: UUID, enabled: bool):
    event = "Cron Job Resumed" if enabled else "Cron Job Paused"
    _mp.track(_str(user_id), event, {**_base_props(organization_id)})


# ── API Keys ──────────────────────────────────────────────────────────────────


@non_breaking_track
def track_api_key_generated(user_id: UUID, organization_id: UUID, scope: str):
    _mp.track(
        _str(user_id),
        "API Key Generated",
        {**_base_props(organization_id), "scope": scope},
    )


# ── OAuth / Integrations ─────────────────────────────────────────────────────


@non_breaking_track
def track_oauth_connection_completed(user_id: UUID, organization_id: UUID, provider: str):
    _mp.track(
        _str(user_id),
        "OAuth Connection Completed",
        {**_base_props(organization_id), "provider": provider},
    )


# ── Monitoring / Observability ────────────────────────────────────────────────


@non_breaking_track
def track_monitoring_loaded(user_id: UUID, project_count: int, organization_id: Optional[UUID] = None):
    _mp.track(
        _str(user_id),
        "Monitoring Loaded",
        {**_base_props(organization_id), "project_count": project_count},
    )


@non_breaking_track
def track_trace_viewed(user_id: UUID, trace_id: UUID):
    _mp.track(_str(user_id), "Trace Viewed", {**_base_props(), "trace_id": _str(trace_id)})
