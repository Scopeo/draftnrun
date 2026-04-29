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
)
from ada_backend.schemas.prompt_schema import (
    DiffOperation,
    PromptDiffResponseSchema,
    PromptPinResponseSchema,
    PromptSectionInputSchema,
    PromptSectionResponseSchema,
    PromptUsageSchema,
    PromptVersionResponseSchema,
    PromptVersionSummarySchema,
)
from ada_backend.services.errors import NotFoundError, PromptStillPinnedError

LOGGER = logging.getLogger(__name__)

_SECTION_PATTERN = re.compile(r"<<section:(\w+)>>")


def _resolve_sections(content: str, sections: list[PromptSectionInputSchema], session: Session) -> str:
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
) -> db.Prompt:
    resolved_content = _resolve_sections(content, sections or [], session)

    prompt = create_prompt(
        session,
        db.Prompt(
            organization_id=organization_id,
            name=name,
            description=description,
            created_by=created_by,
        ),
    )

    create_prompt_version(
        session,
        db.PromptVersion(
            prompt_id=prompt.id,
            version_number=1,
            content=resolved_content,
            created_by=created_by,
        ),
    )

    if sections:
        latest = get_latest_prompt_version(session, prompt.id)
        if latest:
            _create_sections(session, latest.id, sections)

    session.flush()
    return prompt


def create_prompt_version_service(
    session: Session,
    prompt_id: UUID,
    content: str,
    change_description: str | None = None,
    sections: list[PromptSectionInputSchema] | None = None,
    created_by: UUID | None = None,
) -> db.PromptVersion:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt:
        raise NotFoundError(f"Prompt {prompt_id} not found")

    resolved_content = _resolve_sections(content, sections or [], session)
    next_version = get_latest_version_number(session, prompt_id) + 1

    version = create_prompt_version(
        session,
        db.PromptVersion(
            prompt_id=prompt_id,
            version_number=next_version,
            content=resolved_content,
            change_description=change_description,
            created_by=created_by,
        ),
    )

    if sections:
        _create_sections(session, version.id, sections)

    session.flush()
    return version


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


def update_prompt_metadata_service(
    session: Session,
    prompt_id: UUID,
    name: str | None = None,
    description: str | None = None,
) -> db.Prompt:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt:
        raise NotFoundError(f"Prompt {prompt_id} not found")

    if name is not None:
        prompt.name = name
    if description is not None:
        prompt.description = description
    session.flush()
    return prompt


def delete_prompt_service(session: Session, prompt_id: UUID) -> None:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt:
        raise NotFoundError(f"Prompt {prompt_id} not found")

    if is_prompt_pinned(session, prompt_id):
        raise PromptStillPinnedError(prompt_id)

    delete_prompt(session, prompt_id)
    session.flush()


def list_prompts_service(session: Session, organization_id: UUID) -> list[dict]:
    prompts = get_prompts_by_org(session, organization_id)
    result = []
    for p in prompts:
        latest = get_latest_prompt_version(session, p.id)
        result.append({
            "prompt": p,
            "latest_version": PromptVersionSummarySchema.model_validate(latest) if latest else None,
        })
    return result


def get_prompt_detail_service(
    session: Session, prompt_id: UUID
) -> tuple[db.Prompt, list[PromptVersionSummarySchema]]:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt:
        raise NotFoundError(f"Prompt {prompt_id} not found")

    versions = get_prompt_versions(session, prompt_id)
    version_summaries = [PromptVersionSummarySchema.model_validate(v) for v in versions]
    return prompt, version_summaries


def get_prompt_version_detail_service(session: Session, version_id: UUID) -> PromptVersionResponseSchema:
    version = get_prompt_version_by_id(session, version_id)
    if not version:
        raise NotFoundError(f"Prompt version {version_id} not found")

    sections_response = _build_sections_response(session, version)
    return PromptVersionResponseSchema(
        id=version.id,
        prompt_id=version.prompt_id,
        version_number=version.version_number,
        content=version.content,
        change_description=version.change_description,
        created_by=version.created_by,
        created_at=version.created_at,
        sections=sections_response,
    )


def _build_sections_response(session: Session, version: db.PromptVersion) -> list[PromptSectionResponseSchema]:
    result = []
    for section in version.sections:
        section_prompt = get_prompt_by_id(session, section.section_prompt_id)
        section_version = get_prompt_version_by_id(session, section.section_prompt_version_id)
        latest = get_latest_version_number(session, section.section_prompt_id)

        result.append(PromptSectionResponseSchema(
            id=section.id,
            placeholder=section.placeholder,
            section_prompt_id=section.section_prompt_id,
            section_prompt_version_id=section.section_prompt_version_id,
            section_prompt_name=section_prompt.name if section_prompt else None,
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
    session: Session, from_version_id: UUID, to_version_id: UUID
) -> PromptDiffResponseSchema:
    from_version = get_prompt_version_by_id(session, from_version_id)
    if not from_version:
        raise NotFoundError(f"Prompt version {from_version_id} not found")

    to_version = get_prompt_version_by_id(session, to_version_id)
    if not to_version:
        raise NotFoundError(f"Prompt version {to_version_id} not found")

    operations = compute_prompt_diff(from_version.content, to_version.content)

    return PromptDiffResponseSchema(
        from_version_number=from_version.version_number,
        to_version_number=to_version.version_number,
        from_content=from_version.content,
        to_content=to_version.content,
        operations=operations,
    )


def pin_prompt_to_port_service(
    session: Session,
    component_instance_id: UUID,
    port_name: str,
    prompt_version_id: UUID,
) -> None:
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

    session.flush()


def unpin_prompt_from_port_service(
    session: Session,
    component_instance_id: UUID,
    port_name: str,
) -> None:
    ipi = get_input_port_instance(session, component_instance_id, port_name)
    if not ipi:
        raise NotFoundError(f"Input port '{port_name}' not found on component instance {component_instance_id}")

    ipi.prompt_version_id = None
    session.flush()


def get_prompt_usages_service(session: Session, prompt_id: UUID) -> list[PromptUsageSchema]:
    prompt = get_prompt_by_id(session, prompt_id)
    if not prompt:
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
            prompt_name=prompt.name,
            pinned_version_id=pv.id,
            pinned_version_number=pv.version_number,
            latest_version_number=latest_version_number,
            is_latest=pv.version_number == latest_version_number,
        ))
    return result
