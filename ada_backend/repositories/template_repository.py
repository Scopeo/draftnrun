from typing import List, Tuple

from sqlalchemy.orm import Session

from ada_backend.database import models as db

TEMPLATE_ORGANIZATION_ID = "91669f17-430a-447e-a3e9-e7f065c2b54f"


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
