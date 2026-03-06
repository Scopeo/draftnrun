import uuid
from datetime import datetime

from ada_backend.database import models as db
from ada_backend.database.models import CIPHER
from ada_backend.services.variables_service import get_set_service, list_sets_service, upsert_set_service


def _definition(org_id: uuid.UUID, name: str, type: db.VariableType = db.VariableType.STRING) -> db.OrgVariableDefinition:
    return db.OrgVariableDefinition(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=name,
        type=type,
    )


def _set(
    org_id: uuid.UUID,
    set_id: str,
    values: dict,
    encrypted_values: dict | None = None,
) -> db.OrgVariableSet:
    now = datetime.utcnow()
    return db.OrgVariableSet(
        id=uuid.uuid4(),
        organization_id=org_id,
        set_id=set_id,
        values=values,
        encrypted_values=encrypted_values or {},
        created_at=now,
        updated_at=now,
    )


def test_upsert_set_service_encrypts_secret_and_masks_response(mocker):
    org_id = uuid.uuid4()
    definitions = [
        _definition(org_id, "api_url"),
        _definition(org_id, "api_key", type=db.VariableType.SECRET),
    ]
    captured = {}

    def fake_upsert(_session, _organization_id, set_id, values, encrypted_values):
        captured["set_id"] = set_id
        captured["values"] = values
        captured["encrypted_values"] = encrypted_values
        return _set(org_id, set_id, values, encrypted_values)

    mocker.patch("ada_backend.services.variables_service.list_org_definitions", return_value=definitions)
    mocker.patch("ada_backend.services.variables_service.get_org_variable_set", return_value=None)
    mocker.patch("ada_backend.services.variables_service.upsert_org_variable_set", side_effect=fake_upsert)

    response = upsert_set_service(
        session=None,
        organization_id=org_id,
        set_id="neverdrop",
        values={"api_url": "https://example.com", "api_key": "top-secret"},
    )

    assert captured["set_id"] == "neverdrop"
    assert captured["values"] == {"api_url": "https://example.com"}
    assert captured["encrypted_values"]["api_key"] != "top-secret"
    assert CIPHER.decrypt(captured["encrypted_values"]["api_key"].encode()).decode() == "top-secret"
    assert response.values == {
        "api_url": "https://example.com",
        "api_key": {"is_set": True},
    }


def test_upsert_set_service_preserves_existing_secret_when_none(mocker):
    org_id = uuid.uuid4()
    initial_secret = CIPHER.encrypt(b"existing-secret").decode()
    definitions = [
        _definition(org_id, "api_url"),
        _definition(org_id, "api_key", type=db.VariableType.SECRET),
    ]
    existing_set = _set(
        org_id,
        "neverdrop",
        {"api_url": "https://before.example.com"},
        encrypted_values={"api_key": initial_secret},
    )
    captured = {}

    def fake_upsert(_session, _organization_id, set_id, values, encrypted_values):
        captured["values"] = values
        captured["encrypted_values"] = encrypted_values
        return _set(org_id, set_id, values, encrypted_values)

    mocker.patch("ada_backend.services.variables_service.list_org_definitions", return_value=definitions)
    mocker.patch("ada_backend.services.variables_service.get_org_variable_set", return_value=existing_set)
    mocker.patch("ada_backend.services.variables_service.upsert_org_variable_set", side_effect=fake_upsert)

    response = upsert_set_service(
        session=None,
        organization_id=org_id,
        set_id="neverdrop",
        values={"api_url": "https://after.example.com", "api_key": None},
    )

    assert captured["values"] == {"api_url": "https://after.example.com"}
    assert captured["encrypted_values"] == {"api_key": initial_secret}
    assert response.values == {
        "api_url": "https://after.example.com",
        "api_key": {"is_set": True},
    }


def test_get_and_list_set_services_mask_secret_values(mocker):
    org_id = uuid.uuid4()
    definitions = [
        _definition(org_id, "api_url"),
        _definition(org_id, "api_key", type=db.VariableType.SECRET),
    ]
    variable_set = _set(
        org_id,
        "neverdrop",
        {"api_url": "https://example.com", "api_key": "legacy-plaintext"},
        encrypted_values={"api_key": CIPHER.encrypt(b"top-secret").decode()},
    )

    mocker.patch("ada_backend.services.variables_service.list_org_definitions", return_value=definitions)
    mocker.patch("ada_backend.services.variables_service.get_org_variable_set", return_value=variable_set)
    mocker.patch("ada_backend.services.variables_service.list_org_variable_sets", return_value=[variable_set])

    single = get_set_service(session=None, organization_id=org_id, set_id="neverdrop")
    listing = list_sets_service(session=None, organization_id=org_id)

    expected = {"api_url": "https://example.com", "api_key": {"is_set": True}}
    assert single.values == expected
    assert listing.variable_sets[0].values == expected
