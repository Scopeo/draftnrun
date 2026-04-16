import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.project_repository import (
    add_tags_to_project,
    get_project_with_details,
    get_projects_by_organization_with_details,
    get_tags_for_organization,
    insert_project,
    remove_tag_from_project,
    update_project,
)

pytestmark = pytest.mark.skip(
    reason="Tests require PostgreSQL - SQLite doesn't support regex operators (~) used in GraphRunner constraints"
)


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def make_project(ada_backend_mock_session: Session, org_id):
    def _make(name="Test Project", tags=None):
        project_id = uuid.uuid4()
        return insert_project(
            ada_backend_mock_session,
            project_id=project_id,
            project_name=name,
            organization_id=org_id,
            project_type=db.ProjectType.WORKFLOW,
            tags=tags,
        )
    return _make


class TestInsertProjectWithTags:
    def test_create_project_without_tags(self, ada_backend_mock_session, make_project):
        project = make_project()
        assert project.tags == []

    def test_create_project_with_tags(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["foo", "bar"])
        tag_names = sorted(pt.tag for pt in project.tags)
        assert tag_names == ["bar", "foo"]

    def test_tags_are_lowercased(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["GitHub", "CI"])
        tag_names = sorted(pt.tag for pt in project.tags)
        assert tag_names == ["ci", "github"]


class TestUpdateProjectTags:
    def test_replace_tags(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["old"])
        updated = update_project(ada_backend_mock_session, project.id, tags=["new1", "new2"])
        tag_names = sorted(pt.tag for pt in updated.tags)
        assert tag_names == ["new1", "new2"]

    def test_clear_tags(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["keep"])
        updated = update_project(ada_backend_mock_session, project.id, tags=[])
        assert updated.tags == []

    def test_none_tags_leaves_unchanged(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["keep"])
        updated = update_project(ada_backend_mock_session, project.id, project_name="New Name")
        tag_names = [pt.tag for pt in updated.tags]
        assert "keep" in tag_names


class TestAddRemoveTags:
    def test_add_tags(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["existing"])
        result = add_tags_to_project(ada_backend_mock_session, project.id, ["new1", "new2"])
        assert result == ["existing", "new1", "new2"]

    def test_add_duplicate_tags_skipped(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["existing"])
        result = add_tags_to_project(ada_backend_mock_session, project.id, ["existing", "new"])
        assert result == ["existing", "new"]

    def test_remove_tag(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["a", "b", "c"])
        result = remove_tag_from_project(ada_backend_mock_session, project.id, "b")
        assert result == ["a", "c"]

    def test_remove_nonexistent_tag(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["a"])
        result = remove_tag_from_project(ada_backend_mock_session, project.id, "nonexistent")
        assert result == ["a"]


class TestFilterByTags:
    def test_filter_single_tag(self, ada_backend_mock_session, org_id, make_project):
        make_project(name="P1", tags=["github"])
        make_project(name="P2", tags=["manual"])
        results = get_projects_by_organization_with_details(
            ada_backend_mock_session, org_id, type=None, tags=["github"]
        )
        names = [p.project_name for p in results]
        assert "P1" in names
        assert "P2" not in names

    def test_filter_multiple_tags_and_semantics(self, ada_backend_mock_session, org_id, make_project):
        make_project(name="P1", tags=["github", "production"])
        make_project(name="P2", tags=["github"])
        make_project(name="P3", tags=["production"])
        results = get_projects_by_organization_with_details(
            ada_backend_mock_session, org_id, type=None, tags=["github", "production"]
        )
        names = [p.project_name for p in results]
        assert names == ["P1"]

    def test_no_tags_filter_returns_all(self, ada_backend_mock_session, org_id, make_project):
        make_project(name="P1", tags=["a"])
        make_project(name="P2")
        results = get_projects_by_organization_with_details(
            ada_backend_mock_session, org_id, type=None
        )
        assert len(results) == 2


class TestGetProjectWithDetailsTags:
    def test_includes_tags(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["alpha", "beta"])
        result = get_project_with_details(ada_backend_mock_session, project.id)
        assert result.tags == ["alpha", "beta"]


class TestGetTagsForOrganization:
    def test_returns_distinct_tags(self, ada_backend_mock_session, org_id, make_project):
        make_project(name="P1", tags=["github", "shared"])
        make_project(name="P2", tags=["shared", "manual"])
        tags = get_tags_for_organization(ada_backend_mock_session, org_id)
        assert tags == ["github", "manual", "shared"]

    def test_empty_org(self, ada_backend_mock_session):
        tags = get_tags_for_organization(ada_backend_mock_session, uuid.uuid4())
        assert tags == []

    def test_does_not_include_other_org_tags(self, ada_backend_mock_session, org_id, make_project):
        make_project(tags=["mine"])
        other_org = uuid.uuid4()
        insert_project(
            ada_backend_mock_session,
            project_id=uuid.uuid4(),
            project_name="Other",
            organization_id=other_org,
            project_type=db.ProjectType.WORKFLOW,
            tags=["theirs"],
        )
        tags = get_tags_for_organization(ada_backend_mock_session, org_id)
        assert tags == ["mine"]


class TestProjectDeleteCascadesTags:
    def test_tags_deleted_with_project(self, ada_backend_mock_session, make_project):
        project = make_project(tags=["doomed"])
        project_id = project.id
        ada_backend_mock_session.delete(project)
        ada_backend_mock_session.commit()
        remaining = (
            ada_backend_mock_session.query(db.ProjectTag)
            .filter(db.ProjectTag.project_id == project_id)
            .all()
        )
        assert remaining == []
