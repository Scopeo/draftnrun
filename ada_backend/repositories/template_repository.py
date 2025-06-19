from uuid import UUID
from typing import List, Tuple

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def retrieve_production_templates(
    session: Session,
    organization_id: UUID,
) -> List[Tuple[db.Project, db.ProjectEnvironmentBinding]]:

    results = (
        session.query(db.Project, db.ProjectEnvironmentBinding)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.Project.id)
        .filter(
            db.Project.organization_id == organization_id,
            db.ProjectEnvironmentBinding.environment == db.EnvType.PRODUCTION,
        )
        .all()
    )
    return results
