from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ada_backend.database import models as db


def get_prompt_by_id(session: Session, prompt_id: UUID) -> Optional[db.PromptDefinition]:
    return session.query(db.PromptDefinition).filter(db.PromptDefinition.id == prompt_id).first()


def lock_prompt_for_update(session: Session, prompt_id: UUID) -> Optional[db.PromptDefinition]:
    return (
        session.query(db.PromptDefinition)
        .filter(db.PromptDefinition.id == prompt_id)
        .with_for_update()
        .first()
    )


def get_prompts_by_org(session: Session, organization_id: UUID) -> list[db.PromptDefinition]:
    return (
        session.query(db.PromptDefinition)
        .filter(db.PromptDefinition.organization_id == organization_id)
        .all()
    )


def create_prompt(session: Session, prompt: db.PromptDefinition) -> db.PromptDefinition:
    session.add(prompt)
    session.flush()
    return prompt


def delete_prompt(session: Session, prompt_id: UUID) -> None:
    session.query(db.PromptDefinition).filter(db.PromptDefinition.id == prompt_id).delete()
    session.flush()


def get_prompt_version_by_id(session: Session, version_id: UUID) -> Optional[db.PromptVersion]:
    return (
        session.query(db.PromptVersion)
        .options(joinedload(db.PromptVersion.sections))
        .filter(db.PromptVersion.id == version_id)
        .first()
    )


def get_prompt_versions(session: Session, prompt_id: UUID) -> list[db.PromptVersion]:
    return (
        session.query(db.PromptVersion)
        .filter(db.PromptVersion.prompt_id == prompt_id)
        .order_by(db.PromptVersion.version_number.desc())
        .all()
    )


def get_latest_version_number(session: Session, prompt_id: UUID) -> int:
    result = (
        session.query(func.max(db.PromptVersion.version_number))
        .filter(db.PromptVersion.prompt_id == prompt_id)
        .scalar()
    )
    return result or 0


def get_latest_prompt_version(session: Session, prompt_id: UUID) -> Optional[db.PromptVersion]:
    return (
        session.query(db.PromptVersion)
        .filter(db.PromptVersion.prompt_id == prompt_id)
        .order_by(db.PromptVersion.version_number.desc())
        .first()
    )


def create_prompt_version(session: Session, version: db.PromptVersion) -> db.PromptVersion:
    session.add(version)
    session.flush()
    return version


def create_prompt_sections(session: Session, sections: list[db.PromptSection]) -> list[db.PromptSection]:
    session.add_all(sections)
    session.flush()
    return sections


def is_prompt_referenced_in_sections(session: Session, prompt_id: UUID) -> bool:
    return (
        session.query(db.PromptSection.id)
        .filter(db.PromptSection.section_prompt_id == prompt_id)
        .first()
    ) is not None


def is_prompt_pinned(session: Session, prompt_id: UUID) -> bool:
    return (
        session.query(db.InputPortInstance.id)
        .join(db.PromptVersion, db.InputPortInstance.prompt_version_id == db.PromptVersion.id)
        .filter(db.PromptVersion.prompt_id == prompt_id)
        .first()
    ) is not None


def get_prompt_usages(
    session: Session, prompt_id: UUID
) -> list[tuple[db.InputPortInstance, db.PortInstance, db.ComponentInstance, db.PromptVersion]]:
    return (
        session.query(db.InputPortInstance, db.PortInstance, db.ComponentInstance, db.PromptVersion)
        .join(db.PortInstance, db.InputPortInstance.id == db.PortInstance.id)
        .join(db.ComponentInstance, db.PortInstance.component_instance_id == db.ComponentInstance.id)
        .join(db.PromptVersion, db.InputPortInstance.prompt_version_id == db.PromptVersion.id)
        .filter(db.PromptVersion.prompt_id == prompt_id)
        .all()
    )


def get_prompt_pins_for_project(
    session: Session, project_id: UUID
) -> list[tuple[db.InputPortInstance, db.PortInstance, db.PromptVersion, db.PromptDefinition]]:
    return (
        session.query(db.InputPortInstance, db.PortInstance, db.PromptVersion, db.PromptDefinition)
        .join(db.PortInstance, db.InputPortInstance.id == db.PortInstance.id)
        .join(db.ComponentInstance, db.PortInstance.component_instance_id == db.ComponentInstance.id)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
        .join(db.GraphRunner, db.GraphRunner.id == db.GraphRunnerNode.graph_runner_id)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.graph_runner_id == db.GraphRunner.id)
        .join(db.PromptVersion, db.InputPortInstance.prompt_version_id == db.PromptVersion.id)
        .join(db.PromptDefinition, db.PromptVersion.prompt_id == db.PromptDefinition.id)
        .filter(db.ProjectEnvironmentBinding.project_id == project_id)
        .filter(db.InputPortInstance.prompt_version_id.isnot(None))
        .all()
    )


def get_input_port_instance(
    session: Session, component_instance_id: UUID, port_name: str
) -> Optional[db.InputPortInstance]:
    return (
        session.query(db.InputPortInstance)
        .filter(
            db.InputPortInstance.component_instance_id == component_instance_id,
            db.InputPortInstance.name == port_name,
        )
        .first()
    )


def get_input_port_instances_with_prompt_pins(
    session: Session, component_instance_ids: list[UUID]
) -> list[db.InputPortInstance]:
    if not component_instance_ids:
        return []
    return (
        session.query(db.InputPortInstance)
        .options(
            joinedload(db.InputPortInstance.prompt_version).joinedload(db.PromptVersion.prompt),
        )
        .filter(
            db.InputPortInstance.component_instance_id.in_(component_instance_ids),
            db.InputPortInstance.prompt_version_id.isnot(None),
        )
        .all()
    )
