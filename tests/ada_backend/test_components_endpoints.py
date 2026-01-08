from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from ada_backend.database import models as db
from ada_backend.database.setup_db import SessionLocal
from ada_backend.main import app
from ada_backend.repositories.component_repository import get_component_by_id
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


@patch("ada_backend.routers.auth_router.is_user_super_admin")
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


@patch("ada_backend.routers.auth_router.is_user_super_admin")
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

        assert response.status_code == 409
        assert "instance" in response.json()["detail"].lower()

        assert get_component_by_id(test_session, TEST_IDS["component_id"]) is not None
        assert test_session.query(db.ComponentInstance).filter_by(id=instance_id).first() is not None
    finally:
        cleanup_test_entities(test_session, **TEST_IDS)


@patch("ada_backend.routers.auth_router.is_user_super_admin")
def test_delete_nonexistent_component(mock_is_super_admin):
    mock_is_super_admin.return_value = True
    nonexistent_id = UUID("00000000-0000-0000-0000-000000000000")
    response = client.delete(f"/components/{nonexistent_id}", headers=HEADERS_JWT)
    assert response.status_code == 204  # DELETE is idempotent


def create_component_with_multiple_versions(session, component_id, version_ids, param_def_ids=None):
    component = db.Component(
        id=component_id,
        name="Test Component Multiple Versions",
        description="Test component with multiple versions",
        is_agent=False,
        function_callable=False,
        can_use_function_calling=False,
    )
    session.add(component)
    session.flush()

    for idx, version_id in enumerate(version_ids):
        version = db.ComponentVersion(
            id=version_id,
            component_id=component_id,
            version_tag=f"0.0.{idx + 1}",
            description=f"Test version {idx + 1}",
            release_stage=db.ReleaseStage.INTERNAL,
        )
        session.add(version)
        session.flush()

        if param_def_ids and idx < len(param_def_ids):
            param_def = db.ComponentParameterDefinition(
                id=param_def_ids[idx],
                component_version_id=version_id,
                name=f"test_param_{idx}",
                type=db.ParameterType.STRING,
                nullable=False,
                default=f"test_value_{idx}",
                ui_component=db.UIComponent.TEXTFIELD,
            )
            session.add(param_def)
            session.flush()

            global_param = db.ComponentGlobalParameter(
                component_version_id=version_id,
                parameter_definition_id=param_def_ids[idx],
                value=f"global_test_value_{idx}",
            )
            session.add(global_param)

    category = session.query(db.Category).first()
    if category:
        component_category = db.ComponentCategory(component_id=component_id, category_id=category.id)
        session.add(component_category)

    session.commit()


@patch("ada_backend.routers.auth_router.is_user_super_admin")
def test_delete_component_version_one_of_many(mock_is_super_admin, test_session):
    """Test deleting one component version when there are multiple versions."""
    mock_is_super_admin.return_value = True

    component_id = UUID("d8f9e0a1-2c3d-4e5f-9a8b-7c6d5e4f3a2b")
    version_id_1 = UUID("b1c2d3e4-f5a6-4b78-9c8d-7e6f5a4b3c2d")
    version_id_2 = UUID("c2d3e4f5-a6b7-4c89-d0e1-f2a3b4c5d6e7")
    param_def_id_1 = UUID("d3e4f5a6-b7c8-4d9e-a0f1-2b3c4d5e6f7a")
    param_def_id_2 = UUID("e4f5a6b7-c8d9-4e0f-a1b2-3c4d5e6f7a8b")

    try:
        create_component_with_multiple_versions(
            test_session,
            component_id,
            [version_id_1, version_id_2],
            [param_def_id_1, param_def_id_2],
        )

        # Verify both versions exist
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id_1).first() is not None
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id_2).first() is not None
        assert get_component_by_id(test_session, component_id) is not None

        # Delete one version
        response = client.delete(
            f"/components/{component_id}/versions/{version_id_1}",
            headers=HEADERS_JWT,
        )
        assert response.status_code == 204

        test_session.expire_all()

        # Verify deleted version is gone, but component and other version remain
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id_1).first() is None
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id_2).first() is not None
        assert get_component_by_id(test_session, component_id) is not None
    finally:
        # Cleanup remaining entities
        cleanup_test_entities(test_session, component_id, version_id_2, param_def_id_2)
        # Cleanup already deleted version (idempotent - may not exist)
        cleanup_test_entities(test_session, None, version_id_1, param_def_id_1)


@patch("ada_backend.routers.auth_router.is_user_super_admin")
def test_delete_component_version_last_one(mock_is_super_admin, test_session):
    """Test deleting the last component version should delete the component (cascade)."""
    mock_is_super_admin.return_value = True

    component_id = UUID("f9e0a1b2-3d4e-5f6a-0b9c-8d7e6f5a4b3c")
    version_id = UUID("a2b3c4d5-e6f7-4a0b-c1d2-e3f4a5b6c7d8")
    param_def_id = UUID("b3c4d5e6-f7a8-4b0c-d1e2-f3a4b5c6d7e8")

    try:
        create_full_test_component(test_session, component_id, version_id, param_def_id, "Component Single Version")

        # Verify component and version exist
        assert get_component_by_id(test_session, component_id) is not None
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id).first() is not None

        # Delete the only version
        response = client.delete(
            f"/components/{component_id}/versions/{version_id}",
            headers=HEADERS_JWT,
        )
        assert response.status_code == 204

        test_session.expire_all()

        # Verify component is deleted (cascade when last version is deleted)
        assert get_component_by_id(test_session, component_id) is None
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id).first() is None
    except Exception:
        cleanup_test_entities(test_session, component_id, version_id, param_def_id)
        raise


@patch("ada_backend.routers.auth_router.is_user_super_admin")
def test_delete_component_version_with_instances(mock_is_super_admin, test_session):
    """Test deleting component version with instances should fail with 409."""
    mock_is_super_admin.return_value = True

    component_id = UUID("e0a1b2c3-4d5e-6f7a-1b0c-9d8e7f6a5b4c")
    version_id = UUID("c4d5e6f7-a8b9-4c0d-e1f2-a3b4c5d6e7f8")
    param_def_id = UUID("d5e6f7a8-b9c0-4d0e-f1a2-b3c4d5e6f7a8")
    instance_id = UUID("f6a7b8c9-d0e1-4f2a-b3c4-d5e6f7a8b9c0")

    try:
        create_full_test_component(
            test_session, component_id, version_id, param_def_id, "Component Version With Instances"
        )

        # Create an instance
        instance = db.ComponentInstance(
            id=instance_id,
            component_version_id=version_id,
            name="Test Instance",
            ref="test_instance",
        )
        test_session.add(instance)
        test_session.commit()

        assert test_session.query(db.ComponentInstance).filter_by(id=instance_id).first() is not None

        # Try to delete version with instances
        response = client.delete(
            f"/components/{component_id}/versions/{version_id}",
            headers=HEADERS_JWT,
        )

        assert response.status_code == 409
        assert "instance" in response.json()["detail"].lower()

        # Verify component and version still exist
        assert get_component_by_id(test_session, component_id) is not None
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id).first() is not None
        assert test_session.query(db.ComponentInstance).filter_by(id=instance_id).first() is not None
    finally:
        cleanup_test_entities(test_session, component_id, version_id, param_def_id)


@patch("ada_backend.routers.auth_router.is_user_super_admin")
def test_delete_nonexistent_component_version(mock_is_super_admin):
    """Test deleting nonexistent component version should be idempotent (return 204)."""
    mock_is_super_admin.return_value = True

    component_id = UUID("a1b2c3d4-5e6f-7a8b-2c1d-0e9f8a7b6c5d")
    nonexistent_version_id = UUID("00000000-0000-0000-0000-000000000000")

    response = client.delete(
        f"/components/{component_id}/versions/{nonexistent_version_id}",
        headers=HEADERS_JWT,
    )
    assert response.status_code == 204  # DELETE is idempotent


@patch("ada_backend.routers.auth_router.is_user_super_admin")
def test_delete_component_version_mismatched_component_id(mock_is_super_admin, test_session):
    """Test deleting component version with wrong component_id should fail with 400."""
    mock_is_super_admin.return_value = True

    component_id_1 = UUID("b2c3d4e5-6f7a-8b9c-3d2e-1f0a9b8c7d6e")
    component_id_2 = UUID("c3d4e5f6-7a8b-9c0d-4e3f-2a1b0c9d8e7f")
    version_id = UUID("e5f6a7b8-c9d0-4e5f-a6b7-c8d9e0f1a2b3")
    param_def_id = UUID("f6a7b8c9-d0e1-4f6a-b7c8-d9e0f1a2b3c4")

    try:
        # Create component and version
        create_full_test_component(test_session, component_id_1, version_id, param_def_id, "Component Mismatch Test")

        # Try to delete version with wrong component_id
        response = client.delete(
            f"/components/{component_id_2}/versions/{version_id}",
            headers=HEADERS_JWT,
        )

        assert response.status_code == 400
        assert "does not belong" in response.json()["detail"].lower()

        # Verify component and version still exist
        assert get_component_by_id(test_session, component_id_1) is not None
        assert test_session.query(db.ComponentVersion).filter_by(id=version_id).first() is not None
    finally:
        cleanup_test_entities(test_session, component_id_1, version_id, param_def_id)
