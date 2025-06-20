from typing import List, Tuple

from sqlalchemy.orm import Session

from ada_backend.database import models as db

TEMPLATE_ORGANIZATION_ID = "edb9fe43-7000-48c0-aa52-0f6dacf20454" # This is the organization ID for templates


def retrieve_production_templates(
    session: Session,
) -> List[Tuple[db.Project, db.ProjectEnvironmentBinding]]:

    results = (
        session.query(db.Project, db.ProjectEnvironmentBinding)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.Project.id)
        .filter(
            db.Project.organization_id == TEMPLATE_ORGANIZATION_ID,
            db.ProjectEnvironmentBinding.environment == db.EnvType.PRODUCTION,
        )
        .all()
    )
    return results
