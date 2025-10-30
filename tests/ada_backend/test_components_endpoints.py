from uuid import UUID
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from ada_backend.database.setup_db import SessionLocal
from ada_backend.main import app
from ada_backend.repositories.component_repository import get_component_by_id
from ada_backend.database import models as db
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}

TEST_IDS = {
    "component_id": UUID("c7e8f9a0-1b2c-4d5e-8f7a-6b9c8d7e5f4a"),
    "version_id": UUID("a3b4c5d6-e7f8-4901-b2a3-c4d5e6f7a8b9"),
    "param_def_id": UUID("f1e2d3c4-b5a6-4978-a1b2-c3d4e5f6a7b8"),
}


@pytest.fixture
def test_session():
    session = SessionLocal()
    yield session
    session.close()


def cleanup_test_entities(session, component_id=None, version_id=None, param_def_id=None):
    if version_id:
        session.query(db.ComponentInstance).filter(db.ComponentInstance.component_version_id == version_id).delete(
            synchronize_session=False
        )
    if param_def_id:
        session.query(db.BasicParameter).filter(db.BasicParameter.parameter_definition_id == param_def_id).delete(
            synchronize_session=False
        )
        session.query(db.ComponentParameterDefinition).filter(
            db.ComponentParameterDefinition.id == param_def_id
        ).delete(synchronize_session=False)
    if version_id:
        session.query(db.ComponentVersion).filter(db.ComponentVersion.id == version_id).delete(
            synchronize_session=False
        )
    if component_id:
        session.query(db.Component).filter(db.Component.id == component_id).delete(synchronize_session=False)
    session.commit()


def create_full_test_component(session, component_id, version_id, param_def_id, name="Test Component"):
    component = db.Component(
        id=component_id,
        name=name,
        description="Test component description",
        is_agent=False,
        function_callable=False,
        can_use_function_calling=False,
    )
    session.add(component)
    session.flush()

    version = db.ComponentVersion(
        id=version_id,
        component_id=component_id,
        version_tag="0.0.1",
        description="Test version",
        release_stage=db.ReleaseStage.INTERNAL,
    )
    session.add(version)
    session.flush()

    param_def = db.ComponentParameterDefinition(
        id=param_def_id,
        component_version_id=version_id,
        name="test_param",
        type=db.ParameterType.STRING,
        nullable=False,
        default="test_value",
        ui_component=db.UIComponent.TEXTFIELD,
    )
    session.add(param_def)
    session.flush()

    global_param = db.ComponentGlobalParameter(
        component_version_id=version_id,
        parameter_definition_id=param_def_id,
        value="global_test_value",
    )
    session.add(global_param)

    category = session.query(db.Category).first()
    if category:
        component_category = db.ComponentCategory(component_id=component_id, category_id=category.id)
        session.add(component_category)

    session.commit()


def assert_entities_exist(session, component_id, version_id, param_def_id):
    assert get_component_by_id(session, component_id) is not None
    assert session.query(db.ComponentVersion).filter_by(id=version_id).first() is not None
    assert session.query(db.ComponentParameterDefinition).filter_by(id=param_def_id).first() is not None
    assert session.query(db.ComponentGlobalParameter).filter_by(component_version_id=version_id).first() is not None


def assert_entities_deleted(session, component_id, version_id, param_def_id):
    assert get_component_by_id(session, component_id) is None
    assert session.query(db.ComponentVersion).filter_by(id=version_id).first() is None
    assert session.query(db.ComponentParameterDefinition).filter_by(id=param_def_id).first() is None
    assert session.query(db.ComponentGlobalParameter).filter_by(component_version_id=version_id).first() is None
    assert session.query(db.ComponentCategory).filter_by(component_id=component_id).first() is None


@patch("ada_backend.routers.components_router.is_user_super_admin")
def test_delete_component(mock_is_super_admin, test_session):
    mock_is_super_admin.return_value = True

    try:
        create_full_test_component(test_session, **TEST_IDS, name="Test Delete Component")
        assert_entities_exist(test_session, **TEST_IDS)

        response = client.delete(f"/components/{TEST_IDS['component_id']}", headers=HEADERS_JWT)
        assert response.status_code == 204

        test_session.expire_all()
        assert_entities_deleted(test_session, **TEST_IDS)
    except Exception:
        cleanup_test_entities(test_session, **TEST_IDS)
        raise


@patch("ada_backend.routers.components_router.is_user_super_admin")
def test_delete_component_with_instances(mock_is_super_admin, test_session):
    mock_is_super_admin.return_value = True
    instance_id = UUID("e7f8a9b0-c1d2-4345-a6b7-c8d9e0f1a2b3")

    try:
        create_full_test_component(test_session, **TEST_IDS, name="Component With Instances")

        instance = db.ComponentInstance(
            id=instance_id,
            component_version_id=TEST_IDS["version_id"],
            name="Test Instance",
            ref="test_instance",
        )
        test_session.add(instance)
        test_session.commit()

        assert test_session.query(db.ComponentInstance).filter_by(id=instance_id).first() is not None

        response = client.delete(f"/components/{TEST_IDS['component_id']}", headers=HEADERS_JWT)

        assert response.status_code == 400
        assert "instance" in response.json()["detail"].lower()

        assert get_component_by_id(test_session, TEST_IDS["component_id"]) is not None
        assert test_session.query(db.ComponentInstance).filter_by(id=instance_id).first() is not None
    finally:
        cleanup_test_entities(test_session, **TEST_IDS)


@patch("ada_backend.routers.components_router.is_user_super_admin")
def test_delete_nonexistent_component(mock_is_super_admin):
    mock_is_super_admin.return_value = True
    nonexistent_id = UUID("00000000-0000-0000-0000-000000000000")
    response = client.delete(f"/components/{nonexistent_id}", headers=HEADERS_JWT)
    assert response.status_code == 204  # DELETE is idempotent
