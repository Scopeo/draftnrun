import uuid

import pytest

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.prompt_schema import PromptSectionInputSchema
from ada_backend.services.errors import NotFoundError, PromptStillPinnedError
from ada_backend.services.prompt_service import (
    compute_prompt_diff,
    create_prompt_service,
    create_prompt_version_service,
    delete_prompt_service,
    diff_prompt_versions_service,
    get_prompt_detail_service,
    get_prompt_version_detail_service,
    list_prompts_service,
    update_prompt_metadata_service,
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
            prompt = _create_prompt(session)
            session.commit()
            assert prompt.name == "Test Prompt"
            assert prompt.organization_id == ORG_ID

    def test_create_prompt_duplicate_name_raises(self):
        with get_db_session() as session:
            _create_prompt(session, name="Unique Name")
            session.commit()
            with pytest.raises(Exception):
                _create_prompt(session, name="Unique Name")
                session.commit()


class TestListPrompts:
    def test_list_prompts(self):
        org_id = uuid.uuid4()
        with get_db_session() as session:
            create_prompt_service(session, org_id, name="A", content="a", created_by=USER_ID)
            create_prompt_service(session, org_id, name="B", content="b", created_by=USER_ID)
            session.flush()
            results = list_prompts_service(session, org_id)
            assert len(results) == 2


class TestGetPromptDetail:
    def test_get_prompt_detail(self):
        with get_db_session() as session:
            prompt = _create_prompt(session, name=f"Detail-{uuid.uuid4().hex[:8]}")
            session.flush()
            result_prompt, versions = get_prompt_detail_service(session, prompt.id)
            assert result_prompt.name == prompt.name
            assert len(versions) >= 1

    def test_get_nonexistent_prompt_raises(self):
        with get_db_session() as session:
            with pytest.raises(NotFoundError):
                get_prompt_detail_service(session, uuid.uuid4())


class TestUpdatePrompt:
    def test_update_prompt_name(self):
        with get_db_session() as session:
            prompt = _create_prompt(session, name=f"Old-{uuid.uuid4().hex[:8]}")
            session.flush()
            new_name = f"New-{uuid.uuid4().hex[:8]}"
            updated = update_prompt_metadata_service(session, prompt.id, name=new_name)
            assert updated.name == new_name


class TestDeletePrompt:
    def test_delete_prompt(self):
        with get_db_session() as session:
            prompt = _create_prompt(session, name=f"Del-{uuid.uuid4().hex[:8]}")
            session.flush()
            delete_prompt_service(session, prompt.id)
            with pytest.raises(NotFoundError):
                get_prompt_detail_service(session, prompt.id)

    def test_delete_nonexistent_raises(self):
        with get_db_session() as session:
            with pytest.raises(NotFoundError):
                delete_prompt_service(session, uuid.uuid4())


class TestVersioning:
    def test_create_version(self):
        with get_db_session() as session:
            prompt = _create_prompt(session, name=f"Ver-{uuid.uuid4().hex[:8]}")
            session.flush()
            version = create_prompt_version_service(
                session,
                prompt_id=prompt.id,
                content="Updated content",
                change_description="v2",
                created_by=USER_ID,
            )
            session.flush()
            assert version.version_number == 2
            assert version.content == "Updated content"

    def test_get_version_detail(self):
        with get_db_session() as session:
            prompt = _create_prompt(session, name=f"VDet-{uuid.uuid4().hex[:8]}")
            session.flush()
            _, versions = get_prompt_detail_service(session, prompt.id)
            v_id = versions[0].id
            version_detail = get_prompt_version_detail_service(session, v_id)
            assert version_detail.content == "Hello {{name}}"

    def test_get_nonexistent_version_raises(self):
        with get_db_session() as session:
            with pytest.raises(NotFoundError):
                get_prompt_version_detail_service(session, uuid.uuid4())


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
            prompt = _create_prompt(session, name=f"Diff-{uuid.uuid4().hex[:8]}", content="Version 1")
            session.flush()
            v2 = create_prompt_version_service(
                session, prompt_id=prompt.id, content="Version 2", created_by=USER_ID
            )
            session.flush()
            _, versions = get_prompt_detail_service(session, prompt.id)
            v1_id = next(v.id for v in versions if v.version_number == 1)
            diff = diff_prompt_versions_service(session, v1_id, v2.id)
            assert diff.from_version_number == 1
            assert diff.to_version_number == 2
            assert diff.from_content == "Version 1"
            assert diff.to_content == "Version 2"
            assert len(diff.operations) > 0


class TestSections:
    def test_create_prompt_with_sections(self):
        with get_db_session() as session:
            sub_prompt = _create_prompt(session, name=f"Sub-{uuid.uuid4().hex[:8]}", content="Be friendly")
            session.flush()
            _, sub_versions = get_prompt_detail_service(session, sub_prompt.id)
            sub_version_id = sub_versions[0].id

            parent = create_prompt_service(
                session,
                organization_id=ORG_ID,
                name=f"Parent-{uuid.uuid4().hex[:8]}",
                content="You are an assistant.\n\n<<section:tone>>",
                sections=[
                    PromptSectionInputSchema(
                        placeholder="tone",
                        section_prompt_id=sub_prompt.id,
                        section_prompt_version_id=sub_version_id,
                    )
                ],
                created_by=USER_ID,
            )
            session.flush()
            _, parent_versions = get_prompt_detail_service(session, parent.id)
            v_id = parent_versions[0].id
            version_detail = get_prompt_version_detail_service(session, v_id)
            assert "Be friendly" in version_detail.content
            assert "<<section:tone>>" not in version_detail.content
            assert len(version_detail.sections) == 1
            assert version_detail.sections[0].placeholder == "tone"
