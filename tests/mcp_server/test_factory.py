"""Tests for the proxy-tool factory (_factory.py)."""

from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from tests.mcp_server.conftest import FAKE_KEY_ID, FAKE_PROJECT_ID


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


@pytest.fixture
def mcp():
    return FakeMCP()


@pytest.fixture(autouse=True)
def _patch_auth(monkeypatch):
    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-tok", "uid-1"))


# --- Basic GET, auth-only ---


@pytest.mark.asyncio
async def test_auth_only_get(monkeypatch, mcp):
    get_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="get_thing",
            description="Get a thing.",
            method="get",
            path="/things/{thing_id}",
            path_params=(Param("thing_id", str),),
        ),
    ])

    result = await mcp.tools["get_thing"](FAKE_PROJECT_ID)

    assert result == {"ok": True}
    get_mock.assert_awaited_once_with(f"/things/{FAKE_PROJECT_ID}", "jwt-tok", trim=True)


# --- Org-scoped ---


@pytest.mark.asyncio
async def test_org_scoped_get(monkeypatch, mcp):
    org_mock = AsyncMock(return_value={"org_id": "org-1"})
    get_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(_factory, "require_org_context", org_mock)
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="list_things",
            description="List things.",
            method="get",
            path="/orgs/{org_id}/things",
            scope="org",
            return_annotation=list,
        ),
    ])

    result = await mcp.tools["list_things"]()

    assert result == []
    org_mock.assert_awaited_once_with("uid-1")
    get_mock.assert_awaited_once_with("/orgs/org-1/things", "jwt-tok", trim=True)


# --- Role-scoped ---


@pytest.mark.asyncio
async def test_role_scoped_delete(monkeypatch, mcp):
    role_mock = AsyncMock(return_value={"org_id": "org-2"})
    del_mock = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "delete", del_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="delete_thing",
            description="Delete.",
            method="delete",
            path="/orgs/{org_id}/things/{tid}",
            scope="role",
            roles=("admin",),
            path_params=(Param("tid", str),),
        ),
    ])

    await mcp.tools["delete_thing"]("t-99")

    role_mock.assert_awaited_once_with("uid-1", "admin")
    del_mock.assert_awaited_once_with("/orgs/org-2/things/t-99", "jwt-tok", trim=True)


# --- URL encoding ---


@pytest.mark.asyncio
async def test_path_params_are_url_encoded(monkeypatch, mcp):
    get_mock = AsyncMock(return_value={})
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="get_item",
            description="Get.",
            method="get",
            path="/items/{name}",
            path_params=(Param("name", str),),
        ),
    ])

    await mcp.tools["get_item"]("a/b c?d=1")

    get_mock.assert_awaited_once_with("/items/a%2Fb%20c%3Fd%3D1", "jwt-tok", trim=True)


# --- body_param (passthrough) ---


@pytest.mark.asyncio
async def test_body_param_passthrough(monkeypatch, mcp):
    post_mock = AsyncMock(return_value={"id": "new"})
    monkeypatch.setattr(_factory.api, "post", post_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="create_thing",
            description="Create.",
            method="post",
            path="/things",
            body_param=Param("data", dict),
        ),
    ])

    await mcp.tools["create_thing"]({"name": "X"})

    post_mock.assert_awaited_once_with("/things", "jwt-tok", trim=True, json={"name": "X"})


# --- body_fields (assembled dict) ---


@pytest.mark.asyncio
async def test_body_fields_assembled(monkeypatch, mcp):
    del_mock = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(_factory.api, "delete", del_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="revoke_key",
            description="Revoke.",
            method="delete",
            path="/keys",
            body_fields=(Param("key_id", str),),
        ),
    ])

    await mcp.tools["revoke_key"](FAKE_KEY_ID)

    del_mock.assert_awaited_once_with("/keys", "jwt-tok", trim=True, json={"key_id": FAKE_KEY_ID})


# --- body_org_key (org_id injected into body) ---


@pytest.mark.asyncio
async def test_body_org_key_injects_org_id(monkeypatch, mcp):
    org_mock = AsyncMock(return_value={"org_id": "org-5"})
    post_mock = AsyncMock(return_value={"id": "k-new"})
    monkeypatch.setattr(_factory, "require_org_context", org_mock)
    monkeypatch.setattr(_factory.api, "post", post_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="create_org_key",
            description="Create.",
            method="post",
            path="/org-keys",
            scope="org",
            body_fields=(Param("name", str, default=""),),
            body_org_key="organization_id",
        ),
    ])

    await mcp.tools["create_org_key"](name="my-key")

    post_mock.assert_awaited_once_with(
        "/org-keys", "jwt-tok", trim=True,
        json={"name": "my-key", "organization_id": "org-5"},
    )


# --- org_query_key (org_id as query param) ---


@pytest.mark.asyncio
async def test_org_query_key_injects_org_id_as_param(monkeypatch, mcp):
    org_mock = AsyncMock(return_value={"org_id": "org-7"})
    get_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(_factory, "require_org_context", org_mock)
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="list_org_keys",
            description="List.",
            method="get",
            path="/org-keys",
            scope="org",
            org_query_key="organization_id",
            return_annotation=list,
        ),
    ])

    await mcp.tools["list_org_keys"]()

    get_mock.assert_awaited_once_with("/org-keys", "jwt-tok", trim=True, organization_id="org-7")


# --- query_params ---


@pytest.mark.asyncio
async def test_query_params_forwarded(monkeypatch, mcp):
    get_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="list_filtered",
            description="List.",
            method="get",
            path="/items",
            query_params=(Param("status", str, default=None),),
            return_annotation=list,
        ),
    ])

    await mcp.tools["list_filtered"](status="active")
    get_mock.assert_awaited_once_with("/items", "jwt-tok", trim=True, status="active")


@pytest.mark.asyncio
async def test_query_params_none_skipped(monkeypatch, mcp):
    get_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="list_maybe",
            description="List.",
            method="get",
            path="/items",
            query_params=(Param("filter", str, default=None),),
            return_annotation=list,
        ),
    ])

    await mcp.tools["list_maybe"]()
    get_mock.assert_awaited_once_with("/items", "jwt-tok", trim=True)


# --- Handler metadata ---


# --- Validation ---


def test_validate_spec_rejects_unresolved_placeholder(mcp):
    with pytest.raises(ValueError, match="unresolved placeholders"):
        register_proxy_tools(mcp, [
            ToolSpec(
                name="bad_tool",
                description="Bad.",
                method="get",
                path="/things/{thing_id}",
            ),
        ])


def test_validate_spec_rejects_body_org_key_without_org_scope(mcp):
    with pytest.raises(ValueError, match="body_org_key.*requires scope"):
        register_proxy_tools(mcp, [
            ToolSpec(
                name="bad_tool",
                description="Bad.",
                method="post",
                path="/things",
                scope="auth",
                body_org_key="org_id",
            ),
        ])


def test_validate_spec_rejects_role_scope_without_roles(mcp):
    with pytest.raises(ValueError, match="scope='role' requires"):
        register_proxy_tools(mcp, [
            ToolSpec(
                name="bad_tool",
                description="Bad.",
                method="get",
                path="/things",
                scope="role",
            ),
        ])


# --- UUID type annotation ---


def test_uuid_param_annotation_propagated(mcp):
    from uuid import UUID
    register_proxy_tools(mcp, [
        ToolSpec(
            name="get_widget",
            description="Get.",
            method="get",
            path="/widgets/{widget_id}",
            path_params=(Param("widget_id", UUID),),
        ),
    ])

    fn = mcp.tools["get_widget"]
    assert fn.__annotations__["widget_id"] is UUID


# --- None-stripping in body fields ---


@pytest.mark.asyncio
async def test_body_fields_none_values_omitted(monkeypatch, mcp):
    post_mock = AsyncMock(return_value={"id": "new"})
    monkeypatch.setattr(_factory.api, "post", post_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="create_with_optional",
            description="Create.",
            method="post",
            path="/things",
            body_fields=(
                Param("name", str),
                Param("tag", str, default=None),
            ),
        ),
    ])

    await mcp.tools["create_with_optional"](name="X")
    post_mock.assert_awaited_once_with("/things", "jwt-tok", trim=True, json={"name": "X"})


# --- Handler metadata ---


def test_handler_has_correct_name_and_doc(mcp):
    register_proxy_tools(mcp, [
        ToolSpec(
            name="my_tool",
            description="Does something useful.",
            method="get",
            path="/x",
            path_params=(Param("x_id", str, description="The X ID."),),
        ),
    ])

    fn = mcp.tools["my_tool"]
    assert fn.__name__ == "my_tool"
    assert "Does something useful." in fn.__doc__
    assert "x_id: The X ID." in fn.__doc__


# --- trim flag ---


@pytest.mark.asyncio
async def test_trim_false_passed_to_api(monkeypatch, mcp):
    get_mock = AsyncMock(return_value={"big": "data"})
    monkeypatch.setattr(_factory.api, "get", get_mock)

    register_proxy_tools(mcp, [
        ToolSpec(
            name="get_full",
            description="Get.",
            method="get",
            path="/things/{thing_id}",
            path_params=(Param("thing_id", str),),
            trim=False,
        ),
    ])

    await mcp.tools["get_full"](FAKE_PROJECT_ID)
    get_mock.assert_awaited_once_with(f"/things/{FAKE_PROJECT_ID}", "jwt-tok", trim=False)
