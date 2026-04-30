import uuid

import pytest

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.prompt_schema import PromptSectionInputSchema
from ada_backend.services.errors import CrossOrgSectionError, NotFoundError, PromptStillReferencedError
from ada_backend.services.prompt_service import (
    compute_prompt_diff,
    create_prompt_service,
    create_prompt_version_service,
    delete_prompt_service,
    diff_prompt_versions_service,
    get_prompt_detail_service,
    get_prompt_version_detail_service,
    list_prompts_service,
    pin_prompt_to_port_service,
    unpin_prompt_from_port_service,
)

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _create_prompt(session, name="Test Prompt", content="Hello {{name}}"):
    return create_prompt_service(
        session,
        organization_id=ORG_ID,
        name=name,
        content=content,
        created_by=USER_ID,
    )


class TestCreatePrompt:
    def test_create_prompt_basic(self):
        with get_db_session() as session:
            result = _create_prompt(session)
            assert result.latest_version.name == "Test Prompt"
            assert result.organization_id == ORG_ID

    def test_create_prompt_initial_version_has_name(self):
        with get_db_session() as session:
            result = _create_prompt(session, name="Named Prompt")
            assert result.latest_version.name == "Named Prompt"


class TestListPrompts:
    def test_list_prompts(self):
        org_id = uuid.uuid4()
        with get_db_session() as session:
            create_prompt_service(session, org_id, name="A", content="a", created_by=USER_ID)
            create_prompt_service(session, org_id, name="B", content="b", created_by=USER_ID)
            results = list_prompts_service(session, org_id)
            assert len(results) == 2


class TestGetPromptDetail:
    def test_get_prompt_detail(self):
        with get_db_session() as session:
            result = _create_prompt(session, name=f"Detail-{uuid.uuid4().hex[:8]}")
            detail = get_prompt_detail_service(session, result.id, organization_id=ORG_ID)
            assert len(detail.versions) >= 1
            assert detail.versions[0].name.startswith("Detail-")

    def test_get_nonexistent_prompt_raises(self):
        with get_db_session() as session:
            with pytest.raises(NotFoundError):
                get_prompt_detail_service(session, uuid.uuid4(), organization_id=ORG_ID)


class TestDeletePrompt:
    def test_delete_prompt(self):
        with get_db_session() as session:
            result = _create_prompt(session, name=f"Del-{uuid.uuid4().hex[:8]}")
            delete_prompt_service(session, result.id, organization_id=ORG_ID)
            with pytest.raises(NotFoundError):
                get_prompt_detail_service(session, result.id, organization_id=ORG_ID)

    def test_delete_nonexistent_raises(self):
        with get_db_session() as session:
            with pytest.raises(NotFoundError):
                delete_prompt_service(session, uuid.uuid4(), organization_id=ORG_ID)

    def test_delete_prompt_referenced_as_section_raises(self):
        with get_db_session() as session:
            sub = _create_prompt(session, name=f"Sub-{uuid.uuid4().hex[:8]}", content="Be friendly")
            sub_detail = get_prompt_detail_service(session, sub.id, organization_id=ORG_ID)
            sub_version_id = sub_detail.versions[0].id

            create_prompt_service(
                session,
                organization_id=ORG_ID,
                name=f"Parent-{uuid.uuid4().hex[:8]}",
                content="Hello <<section:tone>>",
                sections=[
                    PromptSectionInputSchema(
                        placeholder="tone",
                        section_prompt_id=sub.id,
                        section_prompt_version_id=sub_version_id,
                    )
                ],
                created_by=USER_ID,
            )

            with pytest.raises(PromptStillReferencedError):
                delete_prompt_service(session, sub.id, organization_id=ORG_ID)


class TestVersioning:
    def test_create_version(self):
        with get_db_session() as session:
            result = _create_prompt(session, name=f"Ver-{uuid.uuid4().hex[:8]}")
            version = create_prompt_version_service(
                session,
                prompt_id=result.id,
                name="Updated Name",
                content="Updated content",
                change_description="v2",
                created_by=USER_ID,
                organization_id=ORG_ID,
            )
            assert version.version_number == 2
            assert version.content == "Updated content"
            assert version.name == "Updated Name"

    def test_version_name_independent_from_previous(self):
        with get_db_session() as session:
            result = _create_prompt(session, name="Original Name")
            v2 = create_prompt_version_service(
                session,
                prompt_id=result.id,
                name="Renamed",
                content="v2 content",
                created_by=USER_ID,
                organization_id=ORG_ID,
            )
            detail = get_prompt_detail_service(session, result.id, organization_id=ORG_ID)
            v1_summary = next(v for v in detail.versions if v.version_number == 1)
            assert v1_summary.name == "Original Name"
            assert v2.name == "Renamed"

    def test_get_version_detail(self):
        with get_db_session() as session:
            result = _create_prompt(session, name=f"VDet-{uuid.uuid4().hex[:8]}")
            detail = get_prompt_detail_service(session, result.id, organization_id=ORG_ID)
            v_id = detail.versions[0].id
            version_detail = get_prompt_version_detail_service(session, v_id, organization_id=ORG_ID)
            assert version_detail.content == "Hello {{name}}"

    def test_get_nonexistent_version_raises(self):
        with get_db_session() as session:
            with pytest.raises(NotFoundError):
                get_prompt_version_detail_service(session, uuid.uuid4(), organization_id=ORG_ID)


class TestDiff:
    def test_compute_diff_basic(self):
        ops = compute_prompt_diff("Hello world", "Hello there")
        assert len(ops) > 0
        assert all(op.op in ("insert", "delete", "replace") for op in ops)

    def test_compute_diff_identical(self):
        ops = compute_prompt_diff("same", "same")
        assert len(ops) == 0

    def test_diff_versions_service(self):
        with get_db_session() as session:
            result = _create_prompt(session, name=f"Diff-{uuid.uuid4().hex[:8]}", content="Version 1")
            v2 = create_prompt_version_service(
                session, prompt_id=result.id, name="Diff v2", content="Version 2",
                created_by=USER_ID, organization_id=ORG_ID,
            )
            detail = get_prompt_detail_service(session, result.id, organization_id=ORG_ID)
            v1_id = next(v.id for v in detail.versions if v.version_number == 1)
            diff = diff_prompt_versions_service(session, v1_id, v2.id, organization_id=ORG_ID)
            assert diff.from_version_number == 1
            assert diff.to_version_number == 2
            assert diff.from_content == "Version 1"
            assert diff.to_content == "Version 2"
            assert len(diff.operations) > 0


class TestSections:
    def test_create_prompt_with_sections(self):
        with get_db_session() as session:
            sub_result = _create_prompt(session, name=f"Sub-{uuid.uuid4().hex[:8]}", content="Be friendly")
            sub_detail = get_prompt_detail_service(session, sub_result.id, organization_id=ORG_ID)
            sub_version_id = sub_detail.versions[0].id

            parent_result = create_prompt_service(
                session,
                organization_id=ORG_ID,
                name=f"Parent-{uuid.uuid4().hex[:8]}",
                content="You are an assistant.\n\n<<section:tone>>",
                sections=[
                    PromptSectionInputSchema(
                        placeholder="tone",
                        section_prompt_id=sub_result.id,
                        section_prompt_version_id=sub_version_id,
                    )
                ],
                created_by=USER_ID,
            )
            parent_detail = get_prompt_detail_service(session, parent_result.id, organization_id=ORG_ID)
            v_id = parent_detail.versions[0].id
            version_detail = get_prompt_version_detail_service(session, v_id, organization_id=ORG_ID)
            assert "Be friendly" in version_detail.content
            assert "<<section:tone>>" not in version_detail.content
            assert len(version_detail.sections) == 1
            assert version_detail.sections[0].placeholder == "tone"


class TestCrossOrgSectionRejection:
    def test_section_from_different_org_raises(self):
        other_org_id = uuid.uuid4()
        with get_db_session() as session:
            sub = create_prompt_service(
                session, organization_id=other_org_id, name=f"OtherOrg-{uuid.uuid4().hex[:8]}",
                content="secret content", created_by=USER_ID,
            )
            sub_detail = get_prompt_detail_service(session, sub.id, organization_id=other_org_id)
            sub_version_id = sub_detail.versions[0].id

            with pytest.raises(CrossOrgSectionError):
                create_prompt_service(
                    session,
                    organization_id=ORG_ID,
                    name=f"Parent-{uuid.uuid4().hex[:8]}",
                    content="Hello <<section:tone>>",
                    sections=[
                        PromptSectionInputSchema(
                            placeholder="tone",
                            section_prompt_id=sub.id,
                            section_prompt_version_id=sub_version_id,
                        )
                    ],
                    created_by=USER_ID,
                )

    def test_section_from_same_org_succeeds(self):
        with get_db_session() as session:
            sub = _create_prompt(session, name=f"SameOrg-{uuid.uuid4().hex[:8]}", content="friendly tone")
            sub_detail = get_prompt_detail_service(session, sub.id, organization_id=ORG_ID)
            sub_version_id = sub_detail.versions[0].id

            result = create_prompt_service(
                session,
                organization_id=ORG_ID,
                name=f"Parent-{uuid.uuid4().hex[:8]}",
                content="Hello <<section:tone>>",
                sections=[
                    PromptSectionInputSchema(
                        placeholder="tone",
                        section_prompt_id=sub.id,
                        section_prompt_version_id=sub_version_id,
                    )
                ],
                created_by=USER_ID,
            )
            detail = get_prompt_detail_service(session, result.id, organization_id=ORG_ID)
            v = get_prompt_version_detail_service(session, detail.versions[0].id, organization_id=ORG_ID)
            assert "friendly tone" in v.content


def _setup_graph_with_component(session):
    component = db.Component(id=uuid.uuid4(), name="TestComp")
    session.add(component)
    session.flush()

    cv = db.ComponentVersion(id=uuid.uuid4(), component_id=component.id, version_tag="1.0.0")
    session.add(cv)
    session.flush()

    ci = db.ComponentInstance(id=uuid.uuid4(), component_version_id=cv.id, name="TestCI")
    session.add(ci)
    session.flush()

    port_def = db.PortDefinition(
        id=uuid.uuid4(), component_version_id=cv.id, name="system_prompt", port_type=db.PortType.INPUT,
    )
    session.add(port_def)
    session.flush()

    ipi = db.InputPortInstance(
        id=uuid.uuid4(), component_instance_id=ci.id, name="system_prompt", port_definition_id=port_def.id,
    )
    session.add(ipi)
    session.flush()

    gr = db.GraphRunner(id=uuid.uuid4())
    session.add(gr)
    session.flush()

    node = db.GraphRunnerNode(
        node_id=ci.id, graph_runner_id=gr.id, node_type=db.NodeType.COMPONENT, is_start_node=True,
    )
    session.add(node)
    session.flush()

    return ci, gr, ipi


class TestPinOwnershipValidation:
    def test_pin_with_wrong_graph_runner_raises(self):
        with get_db_session() as session:
            ci, gr, ipi = _setup_graph_with_component(session)
            prompt = _create_prompt(session, name=f"Pin-{uuid.uuid4().hex[:8]}")
            detail = get_prompt_detail_service(session, prompt.id, organization_id=ORG_ID)
            version_id = detail.versions[0].id

            wrong_graph_runner_id = uuid.uuid4()
            with pytest.raises(NotFoundError, match="not found in graph"):
                pin_prompt_to_port_service(session, ci.id, "system_prompt", version_id, wrong_graph_runner_id)

    def test_unpin_with_wrong_graph_runner_raises(self):
        with get_db_session() as session:
            ci, gr, ipi = _setup_graph_with_component(session)

            wrong_graph_runner_id = uuid.uuid4()
            with pytest.raises(NotFoundError, match="not found in graph"):
                unpin_prompt_from_port_service(session, ci.id, "system_prompt", wrong_graph_runner_id)

    def test_pin_with_correct_graph_runner_succeeds(self):
        with get_db_session() as session:
            ci, gr, ipi = _setup_graph_with_component(session)
            prompt = _create_prompt(session, name=f"Pin-{uuid.uuid4().hex[:8]}")
            detail = get_prompt_detail_service(session, prompt.id, organization_id=ORG_ID)
            version_id = detail.versions[0].id

            pin_prompt_to_port_service(session, ci.id, "system_prompt", version_id, gr.id)
            session.refresh(ipi)
            assert ipi.prompt_version_id == version_id
