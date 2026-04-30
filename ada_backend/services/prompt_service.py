import logging
import re
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.prompt_repository import (
    create_prompt,
    create_prompt_sections,
    create_prompt_version,
    delete_prompt,
    get_input_port_instance,
    get_latest_prompt_version,
    get_latest_version_number,
    get_prompt_by_id,
    get_prompt_pins_for_project,
    get_prompt_usages,
    get_prompt_version_by_id,
    get_prompt_versions,
    get_prompts_by_org,
    is_prompt_pinned,
    is_prompt_referenced_in_sections,
    lock_prompt_for_update,
)
from ada_backend.schemas.prompt_schema import (
    DiffOperation,
    PromptDetailResponseSchema,
    PromptDiffResponseSchema,
    PromptPinResponseSchema,
    PromptResponseSchema,
    PromptSectionInputSchema,
    PromptSectionResponseSchema,
    PromptUsageSchema,
    PromptVersionResponseSchema,
    PromptVersionSummarySchema,
)
from ada_backend.services.errors import (
    CrossOrgSectionError,
    NotFoundError,
    PromptStillPinnedError,
    PromptStillReferencedError,
)

LOGGER = logging.getLogger(__name__)

_SECTION_PATTERN = re.compile(r"<<section:(\w+)>>")


def _resolve_sections(
    content: str, sections: list[PromptSectionInputSchema], session: Session, parent_org_id: UUID
) -> str:
    if not sections:
        return content

    section_map: dict[str, str] = {}
    for s in sections:
        version = get_prompt_version_by_id(session, s.section_prompt_version_id)
        if not version:
            raise NotFoundError(f"Prompt version {s.section_prompt_version_id} not found")
        if version.prompt_id != s.section_prompt_id:
            raise ValueError(
                f"Version {s.section_prompt_version_id} does not belong to prompt {s.section_prompt_id}"
            )
        section_prompt = get_prompt_by_id(session, version.prompt_id)
        if not section_prompt or section_prompt.organization_id != parent_org_id:
            raise CrossOrgSectionError(s.section_prompt_id)
        section_map[s.placeholder] = version.content

    def _replacer(match: re.Match) -> str:
        placeholder = match.group(1)
        if placeholder in section_map:
            return section_map[placeholder]
        return match.group(0)

    return _SECTION_PATTERN.sub(_replacer, content)


def create_prompt_service(
    session: Session,
    organization_id: UUID,
    name: str,
    content: str,
    description: str | None = None,
    sections: list[PromptSectionInputSchema] | None = None,
    created_by: UUID | None = None,
) -> PromptResponseSchema:
    resolved_content = _resolve_sections(content, sections or [], session, parent_org_id=organization_id)

    prompt = create_prompt(
        session,
        db.PromptDefinition(
            organization_id=organization_id,
        ),
    )

    create_prompt_version(
        session,
        db.PromptVersion(
            prompt_id=prompt.id,
            version_number=1,
            name=name,
            description=description,
            content=resolved_content,
            created_by=created_by,
        ),
    )

    if sections:
        latest = get_latest_prompt_version(session, prompt.id)
        if latest:
            _create_sections(session, latest.id, sections)

    session.commit()
    latest = get_latest_prompt_version(session, prompt.id)
    return PromptResponseSchema(
        id=prompt.id,
        organization_id=prompt.organization_id,
        latest_version=PromptVersionSummarySchema.model_validate(latest) if latest else None,
    )


def create_prompt_version_service(
    session: Session,
    prompt_id: UUID,
    name: str,
    content: str,
    description: str | None = None,
    change_description: str | None = None,
    sections: list[PromptSectionInputSchema] | None = None,
    created_by: UUID | None = None,
    organization_id: UUID | None = None,
) -> PromptVersionResponseSchema:
    prompt = lock_prompt_for_update(session, prompt_id)
    if not prompt or (organization_id and prompt.organization_id != organization_id):
        raise NotFoundError(f"Prompt {prompt_id} not found")

    resolved_content = _resolve_sections(content, sections or [], session, parent_org_id=prompt.organization_id)
    next_version = get_latest_version_number(session, prompt_id) + 1

    version = create_prompt_version(
        session,
        db.PromptVersion(
            prompt_id=prompt_id,
            version_number=next_version,
            name=name,
            description=description,
            content=resolved_content,
            change_description=change_description,
            created_by=created_by,
        ),
    )

    if sections:
        _create_sections(session, version.id, sections)

    session.commit()
    return get_prompt_version_detail_service(session, version.id, organization_id=prompt.organization_id)


def _create_sections(
    session: Session, version_id: UUID, sections: list[PromptSectionInputSchema]
) -> list[db.PromptSection]:
    section_models = [
        db.PromptSection(
            prompt_version_id=version_id,
            section_prompt_id=s.section_prompt_id,
            section_prompt_version_id=s.section_prompt_version_id,
            placeholder=s.placeholder,
            position=i,
        )
        for i, s in enumerate(sections)
    ]
    return create_prompt_sections(session, section_models)


def delete_prompt_service(session: Session, prompt_id: UUID, organization_id: UUID | None = None) -> None:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt or (organization_id and prompt.organization_id != organization_id):
        raise NotFoundError(f"Prompt {prompt_id} not found")

    if is_prompt_pinned(session, prompt_id):
        raise PromptStillPinnedError(prompt_id)

    if is_prompt_referenced_in_sections(session, prompt_id):
        raise PromptStillReferencedError(prompt_id)

    delete_prompt(session, prompt_id)
    session.commit()


def list_prompts_service(session: Session, organization_id: UUID) -> list[PromptResponseSchema]:
    prompts = get_prompts_by_org(session, organization_id)
    return [
        PromptResponseSchema(
            id=p.id,
            organization_id=p.organization_id,
            latest_version=PromptVersionSummarySchema.model_validate(latest) if latest else None,
        )
        for p in prompts
        for latest in [get_latest_prompt_version(session, p.id)]
    ]


def get_prompt_detail_service(
    session: Session, prompt_id: UUID, organization_id: UUID | None = None
) -> PromptDetailResponseSchema:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt or (organization_id and prompt.organization_id != organization_id):
        raise NotFoundError(f"Prompt {prompt_id} not found")

    versions = get_prompt_versions(session, prompt_id)
    version_summaries = [PromptVersionSummarySchema.model_validate(v) for v in versions]
    return PromptDetailResponseSchema(
        id=prompt.id,
        organization_id=prompt.organization_id,
        latest_version=version_summaries[0] if version_summaries else None,
        versions=version_summaries,
    )


def list_prompt_versions_service(
    session: Session, prompt_id: UUID, organization_id: UUID | None = None
) -> list[PromptVersionSummarySchema]:
    if organization_id:
        prompt = get_prompt_by_id(session, prompt_id)
        if not prompt or prompt.organization_id != organization_id:
            raise NotFoundError(f"Prompt {prompt_id} not found")
    versions = get_prompt_versions(session, prompt_id)
    return [PromptVersionSummarySchema.model_validate(v) for v in versions]


def get_prompt_version_detail_service(
    session: Session, version_id: UUID, organization_id: UUID | None = None
) -> PromptVersionResponseSchema:
    version = get_prompt_version_by_id(session, version_id)
    if not version:
        raise NotFoundError(f"Prompt version {version_id} not found")
    if organization_id:
        prompt = get_prompt_by_id(session, version.prompt_id)
        if not prompt or prompt.organization_id != organization_id:
            raise NotFoundError(f"Prompt version {version_id} not found")

    sections_response = _build_sections_response(session, version)
    return PromptVersionResponseSchema(
        id=version.id,
        prompt_id=version.prompt_id,
        version_number=version.version_number,
        name=version.name,
        description=version.description,
        content=version.content,
        change_description=version.change_description,
        created_by=version.created_by,
        created_at=version.created_at,
        sections=sections_response,
    )


def _build_sections_response(session: Session, version: db.PromptVersion) -> list[PromptSectionResponseSchema]:
    result = []
    for section in version.sections:
        section_latest_version = get_latest_prompt_version(session, section.section_prompt_id)
        section_version = get_prompt_version_by_id(session, section.section_prompt_version_id)
        latest = get_latest_version_number(session, section.section_prompt_id)

        result.append(PromptSectionResponseSchema(
            id=section.id,
            placeholder=section.placeholder,
            section_prompt_id=section.section_prompt_id,
            section_prompt_version_id=section.section_prompt_version_id,
            section_prompt_name=section_latest_version.name if section_latest_version else None,
            section_version_number=section_version.version_number if section_version else None,
            latest_version_number=latest,
            is_latest=section_version.version_number == latest if section_version else False,
            position=section.position,
        ))
    return result


def compute_prompt_diff(from_content: str, to_content: str) -> list[DiffOperation]:
    matcher = SequenceMatcher(None, from_content, to_content)
    return [
        DiffOperation(op=op, from_start=i1, from_end=i2, to_start=j1, to_end=j2)
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
        if op != "equal"
    ]


def diff_prompt_versions_service(
    session: Session, from_version_id: UUID, to_version_id: UUID, organization_id: UUID | None = None
) -> PromptDiffResponseSchema:
    from_version = get_prompt_version_by_id(session, from_version_id)
    if not from_version:
        raise NotFoundError(f"Prompt version {from_version_id} not found")

    to_version = get_prompt_version_by_id(session, to_version_id)
    if not to_version:
        raise NotFoundError(f"Prompt version {to_version_id} not found")

    if organization_id:
        for v in (from_version, to_version):
            prompt = get_prompt_by_id(session, v.prompt_id)
            if not prompt or prompt.organization_id != organization_id:
                raise NotFoundError(f"Prompt version {v.id} not found")

    operations = compute_prompt_diff(from_version.content, to_version.content)

    return PromptDiffResponseSchema(
        from_version_number=from_version.version_number,
        to_version_number=to_version.version_number,
        from_content=from_version.content,
        to_content=to_version.content,
        operations=operations,
    )


def _verify_component_in_graph(session: Session, component_instance_id: UUID, graph_runner_id: UUID) -> None:
    node = (
        session.query(db.GraphRunnerNode)
        .filter(
            db.GraphRunnerNode.graph_runner_id == graph_runner_id,
            db.GraphRunnerNode.node_id == component_instance_id,
        )
        .first()
    )
    if not node:
        raise NotFoundError(
            f"Component instance {component_instance_id} not found in graph {graph_runner_id}"
        )


def pin_prompt_to_port_service(
    session: Session,
    component_instance_id: UUID,
    port_name: str,
    prompt_version_id: UUID,
    graph_runner_id: UUID,
) -> None:
    _verify_component_in_graph(session, component_instance_id, graph_runner_id)
    ipi = get_input_port_instance(session, component_instance_id, port_name)
    if not ipi:
        raise NotFoundError(f"Input port '{port_name}' not found on component instance {component_instance_id}")

    version = get_prompt_version_by_id(session, prompt_version_id)
    if not version:
        raise NotFoundError(f"Prompt version {prompt_version_id} not found")

    ipi.prompt_version_id = prompt_version_id

    literal_json = {"type": "literal", "value": version.content}
    if ipi.field_expression:
        ipi.field_expression.expression_json = literal_json
    else:
        fe = db.FieldExpression(expression_json=literal_json)
        session.add(fe)
        session.flush()
        ipi.field_expression_id = fe.id

    session.commit()


def unpin_prompt_from_port_service(
    session: Session,
    component_instance_id: UUID,
    port_name: str,
    graph_runner_id: UUID,
) -> None:
    _verify_component_in_graph(session, component_instance_id, graph_runner_id)
    ipi = get_input_port_instance(session, component_instance_id, port_name)
    if not ipi:
        raise NotFoundError(f"Input port '{port_name}' not found on component instance {component_instance_id}")

    ipi.prompt_version_id = None
    session.commit()


def get_prompt_usages_service(
    session: Session, prompt_id: UUID, organization_id: UUID | None = None
) -> list[PromptUsageSchema]:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt or (organization_id and prompt.organization_id != organization_id):
        raise NotFoundError(f"Prompt {prompt_id} not found")

    usages = get_prompt_usages(session, prompt_id)
    result = []
    for ipi, pi, ci, pv in usages:
        project_info = _get_project_for_component_instance(session, ci.id)
        result.append(PromptUsageSchema(
            project_id=project_info[0] if project_info else UUID(int=0),
            project_name=project_info[1] if project_info else "Unknown",
            component_instance_id=ci.id,
            component_instance_name=ci.name,
            port_name=pi.name,
            pinned_version_id=pv.id,
            pinned_version_number=pv.version_number,
        ))
    return result


def _get_project_for_component_instance(session: Session, component_instance_id: UUID) -> tuple[UUID, str] | None:
    result = (
        session.query(db.Project.id, db.Project.name)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.Project.id)
        .join(db.GraphRunner, db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.graph_runner_id == db.GraphRunner.id)
        .filter(db.GraphRunnerNode.node_id == component_instance_id)
        .first()
    )
    return result


def get_project_prompt_pins_service(session: Session, project_id: UUID) -> list[PromptPinResponseSchema]:
    pins = get_prompt_pins_for_project(session, project_id)
    result = []
    for ipi, pi, pv, prompt in pins:
        ci = (
            session.query(db.ComponentInstance)
            .filter(db.ComponentInstance.id == pi.component_instance_id)
            .first()
        )
        latest_version_number = get_latest_version_number(session, prompt.id)
        result.append(PromptPinResponseSchema(
            port_name=pi.name,
            component_instance_id=pi.component_instance_id,
            component_instance_name=ci.name if ci else None,
            prompt_id=prompt.id,
            prompt_name=pv.name,
            pinned_version_id=pv.id,
            pinned_version_number=pv.version_number,
            latest_version_number=latest_version_number,
            is_latest=pv.version_number == latest_version_number,
        ))
    return result
