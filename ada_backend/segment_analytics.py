from uuid import UUID
import logging

import segment.analytics as analytics

from settings import settings


LOGGER = logging.getLogger(__name__)
if hasattr(settings, "SEGMENT_API_KEY") and hasattr(settings, "ENV"):
    analytics.write_key = settings.SEGMENT_API_KEY
    analytics_enabled = True
else:
    analytics_enabled = False


def non_breaking_track(func):
    def track_without_break(*args, **kwargs):
        if not analytics_enabled:
            LOGGER.debug(f"Segment analytics is disabled, skipping tracking of {func.__name__}")
            return
        try:
            LOGGER.debug(f"Tracking event: {func.__name__}")
            return func(*args, **kwargs)
        except Exception as e:
            LOGGER.warning(f"Warning: tracking was unsuccessful: {e}")
            return None

    return track_without_break


@non_breaking_track
def identify_user_access_org(user_id: UUID, user_email: str, organization_id: UUID):
    analytics.identify(user_id=str(user_id), traits={"email": user_email})
    analytics.group(user_id=str(user_id), group_id=str(organization_id))


@non_breaking_track
def track_user_get_project_list(user_id: UUID, organization_id: UUID):
    analytics.track(
        user_id=str(user_id),
        event="Project List Loaded",
        properties={
            "env": settings.ENV,
            "organization_id": str(organization_id),
        },
    )


@non_breaking_track
def track_project_created(user_id: UUID, organization_id: UUID, project_id: UUID, project_name: str):
    analytics.track(
        user_id=str(user_id),
        event="Project Created",
        properties={
            "env": settings.ENV,
            "organization_id": str(organization_id),
            "project_id": str(project_id),
            "project_name": project_name,
        },
    )


@non_breaking_track
def track_project_loaded(user_id: UUID, project_id: UUID):
    analytics.track(
        user_id=str(user_id),
        event="Project Loaded",
        properties={
            "env": settings.ENV,
            "project_id": str(project_id),
        },
    )


@non_breaking_track
def track_project_saved(user_id: UUID, project_id: UUID):
    analytics.track(
        user_id=str(user_id),
        event="Project Saved",
        properties={
            "env": settings.ENV,
            "project_id": str(project_id),
        },
    )


@non_breaking_track
def track_project_monitoring_loaded(user_id: UUID, project_id: UUID):
    analytics.track(
        user_id=str(user_id),
        event="Monitoring Loaded",
        properties={
            "env": settings.ENV,
            "project_id": str(project_id),
        },
    )


@non_breaking_track
def track_project_observability_loaded(user_id: UUID, project_id: UUID):
    analytics.track(
        user_id=str(user_id),
        event="Observability Loaded",
        properties={
            "env": settings.ENV,
            "project_id": str(project_id),
        },
    )


@non_breaking_track
def track_ingestion_task_created(user_id: UUID, organization_id: UUID, task_id: UUID):
    analytics.track(
        user_id=str(user_id),
        event="Ingestion Task Created",
        properties={
            "env": settings.ENV,
            "organization_id": str(organization_id),
            "task_id": str(task_id),
        },
    )
