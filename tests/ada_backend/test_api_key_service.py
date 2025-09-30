from uuid import uuid4

import pytest

from sqlalchemy.orm import Session
from ada_backend.services import api_key_service as service
from ada_backend.database import models as db


class DummySession:
    pass


def test_hash_and_verify_consistency():
    key = "taylor_testkey"
    hashed = service._hash_key(key)
    # hashing same key twice gives same result
    assert hashed == service._hash_key(key)
    # different key -> different hash
    assert hashed != service._hash_key(key + "x")


def test_generate_api_key_format():
    api_key = service._generate_api_key()
    assert api_key.startswith(service.API_KEY_PREFIX)
    # encoded part should be urlsafe base64 without padding
    body = api_key[len(service.API_KEY_PREFIX) :]
    assert "=" not in body
    # length should be at least bytes*4/3 approx
    assert len(body) >= service.API_KEY_BYTES * 4 // 3 - 1


def test_get_api_keys_service_project(monkeypatch):
    # create fake keys returned from repo
    fake_key = type("K", (), {"id": uuid4(), "name": "k1"})()

    def fake_get_by_project(session, project_id):
        assert isinstance(session, Session) or isinstance(session, DummySession)
        return [fake_key]

    monkeypatch.setattr(service, "get_api_keys_by_project_id", fake_get_by_project)

    resp = service.get_api_keys_service(DummySession(), project_id=uuid4())
    assert resp.project_id is not None
    assert resp.organization_id is None
    assert len(resp.api_keys) == 1
    assert resp.api_keys[0].key_name == "k1"


def test_get_api_keys_service_org(monkeypatch):
    fake_key = type("K", (), {"id": uuid4(), "name": "orgk"})()

    def fake_get_by_org(session, org_id):
        return [fake_key]

    monkeypatch.setattr(service, "get_api_keys_by_org_id", fake_get_by_org)

    resp = service.get_api_keys_service(DummySession(), organization_id=uuid4())
    assert resp.project_id is None
    assert resp.organization_id is not None
    assert len(resp.api_keys) == 1
    assert resp.api_keys[0].key_name == "orgk"


def test_generate_scoped_api_key_and_storage(monkeypatch):
    created_id = uuid4()

    def fake_create(session, scope_type, scope_id, key_name, hashed_key, creator_user_id):
        assert scope_type in (db.ApiKeyType.PROJECT, db.ApiKeyType.ORGANIZATION)
        assert key_name == "name"
        assert isinstance(hashed_key, str) and len(hashed_key) == 64
        return created_id

    monkeypatch.setattr(service, "create_api_key", fake_create)

    resp = service.generate_scoped_api_key(DummySession(), db.ApiKeyType.PROJECT, uuid4(), "name", uuid4())
    assert resp.key_id == created_id
    assert resp.private_key.startswith(service.API_KEY_PREFIX)


def test_verify_api_key_project(monkeypatch):
    # create a private key and its hash
    private = service._generate_api_key()
    hashed = service._hash_key(private)

    # fake returned api_key object as ProjectApiKey
    proj_id = uuid4()

    # create a real mapped instance so SQLAlchemy instrumentation is present
    api_obj = db.ProjectApiKey()
    api_obj.id = uuid4()
    api_obj.is_active = True
    api_obj.project_id = proj_id
    api_obj.type = db.ApiKeyType.PROJECT

    def fake_get_by_hashed(session, hashed_key):
        assert hashed_key == hashed
        return api_obj

    def fake_get_project(session, hashed_key):
        return type("Pr", (), {"id": proj_id})()

    monkeypatch.setattr(service, "get_api_key_by_hashed_key", fake_get_by_hashed)
    monkeypatch.setattr(service, "get_project_by_api_key", fake_get_project)

    v = service.verify_api_key(DummySession(), private)
    assert v.scope_type == db.ApiKeyType.PROJECT
    assert v.project_id == proj_id


def test_verify_api_key_org(monkeypatch):
    private = service._generate_api_key()

    org_id = uuid4()

    # create a real mapped instance so SQLAlchemy instrumentation is present
    api_obj = db.OrgApiKey()
    api_obj.id = uuid4()
    api_obj.is_active = True
    api_obj.organization_id = org_id
    api_obj.type = db.ApiKeyType.ORGANIZATION

    def fake_get_by_hashed(session, hashed_key):
        return api_obj

    monkeypatch.setattr(service, "get_api_key_by_hashed_key", fake_get_by_hashed)

    v = service.verify_api_key(DummySession(), private)
    assert v.scope_type == db.ApiKeyType.ORGANIZATION
    assert v.organization_id == org_id


def test_deactivate_api_key_service(monkeypatch):
    did = uuid4()

    def fake_deactivate(session, key_id, revoker_user_id):
        assert key_id == did
        return key_id

    monkeypatch.setattr(service, "deactivate_api_key", fake_deactivate)

    out = service.deactivate_api_key_service(DummySession(), did, uuid4())
    assert out == did


def test_verify_ingestion_api_key():
    private = "taylor_ingest"
    hashed = service.verify_ingestion_api_key(private)
    assert hashed == service._hash_key(private)


# Edge cases


def test_get_api_keys_service_invalid_args():
    with pytest.raises(ValueError):
        service.get_api_keys_service(DummySession())
    with pytest.raises(ValueError):
        service.get_api_keys_service(DummySession(), project_id=uuid4(), organization_id=uuid4())


def test_verify_api_key_invalid(monkeypatch):
    # missing key -> repository returns None
    def fake_get_none(session, hashed_key):
        return None

    monkeypatch.setattr(service, "get_api_key_by_hashed_key", fake_get_none)
    with pytest.raises(ValueError):
        service.verify_api_key(DummySession(), "doesnotexist")
