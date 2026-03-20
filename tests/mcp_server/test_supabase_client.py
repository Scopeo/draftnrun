import httpx
import pytest

from mcp_server.auth import supabase_client

FAKE_JWT = "fake-jwt-token"
FAKE_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FAKE_ORG_ID = "11111111-1111-1111-1111-111111111111"
FAKE_ORG_ID_2 = "22222222-2222-2222-2222-222222222222"


class FakeSettings:
    SUPABASE_PROJECT_URL = "https://fake.supabase.co"
    SUPABASE_PROJECT_KEY = "fake-anon-key"
    MCP_REQUEST_TIMEOUT = 5


class FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or (str(json_data) if json_data else "")

    def json(self):
        return self._json_data


class FakeAsyncClient:
    """Records requests and returns pre-configured responses by URL substring."""

    def __init__(self, responses: dict[str, FakeResponse]):
        self._responses = responses
        self.requests: list[dict] = []

    async def get(self, url, *, headers=None, params=None):
        self.requests.append({"method": "GET", "url": url, "headers": headers, "params": params})
        return self._match(url)

    async def post(self, url, *, headers=None, json=None):
        self.requests.append({"method": "POST", "url": url, "headers": headers, "json": json})
        return self._match(url)

    def _match(self, url: str) -> FakeResponse:
        for substring, resp in self._responses.items():
            if substring in url:
                return resp
        raise AssertionError(f"No fake response configured for URL: {url}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    monkeypatch.setattr(supabase_client, "settings", FakeSettings())


# ---------------------------------------------------------------------------
# list_user_organizations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_user_organizations_happy_path(monkeypatch):
    client = FakeAsyncClient({
        "organization_members": FakeResponse(200, json_data=[
            {"org_id": FAKE_ORG_ID, "role": "admin"},
            {"org_id": FAKE_ORG_ID_2, "role": "member"},
        ]),
        "organizations": FakeResponse(200, json_data=[
            {"id": FAKE_ORG_ID, "name": "Org One"},
            {"id": FAKE_ORG_ID_2, "name": "Org Two"},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.list_user_organizations(FAKE_JWT, FAKE_USER_ID)

    assert result == [
        {"id": FAKE_ORG_ID, "name": "Org One", "role": "admin"},
        {"id": FAKE_ORG_ID_2, "name": "Org Two", "role": "member"},
    ]
    assert len(client.requests) == 2
    assert "organization_members" in client.requests[0]["url"]
    assert client.requests[0]["params"]["user_id"] == f"eq.{FAKE_USER_ID}"


@pytest.mark.asyncio
async def test_list_user_organizations_memberships_fail(monkeypatch):
    client = FakeAsyncClient({
        "organization_members": FakeResponse(500, text="Internal Server Error"),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    with pytest.raises(ValueError, match="Failed to fetch your organization memberships"):
        await supabase_client.list_user_organizations(FAKE_JWT, FAKE_USER_ID)


@pytest.mark.asyncio
async def test_list_user_organizations_empty_memberships(monkeypatch):
    client = FakeAsyncClient({
        "organization_members": FakeResponse(200, json_data=[]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.list_user_organizations(FAKE_JWT, FAKE_USER_ID)

    assert result == []


@pytest.mark.asyncio
async def test_list_user_organizations_invalid_uuid_skipped(monkeypatch):
    client = FakeAsyncClient({
        "organization_members": FakeResponse(200, json_data=[
            {"org_id": "not-a-uuid", "role": "admin"},
            {"org_id": FAKE_ORG_ID, "role": "member"},
        ]),
        "organizations": FakeResponse(200, json_data=[
            {"id": FAKE_ORG_ID, "name": "Valid Org"},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.list_user_organizations(FAKE_JWT, FAKE_USER_ID)

    assert result == [{"id": FAKE_ORG_ID, "name": "Valid Org", "role": "member"}]


@pytest.mark.asyncio
async def test_list_user_organizations_all_uuids_invalid(monkeypatch):
    client = FakeAsyncClient({
        "organization_members": FakeResponse(200, json_data=[
            {"org_id": "garbage", "role": "admin"},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.list_user_organizations(FAKE_JWT, FAKE_USER_ID)

    assert result == []


@pytest.mark.asyncio
async def test_list_user_organizations_orgs_fetch_fail(monkeypatch):
    client = FakeAsyncClient({
        "organization_members": FakeResponse(200, json_data=[
            {"org_id": FAKE_ORG_ID, "role": "admin"},
        ]),
        "organizations": FakeResponse(502, text="Bad Gateway"),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    with pytest.raises(ValueError, match="Failed to fetch organization details"):
        await supabase_client.list_user_organizations(FAKE_JWT, FAKE_USER_ID)


# ---------------------------------------------------------------------------
# get_org_members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_org_members_happy_path(monkeypatch):
    members = [{"user_id": "u1", "role": "admin"}, {"user_id": "u2", "role": "member"}]
    client = FakeAsyncClient({
        "get-organization-members-details": FakeResponse(200, json_data=members),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.get_org_members(FAKE_JWT, FAKE_ORG_ID)

    assert result == members
    req = client.requests[0]
    assert req["method"] == "POST"
    assert req["json"] == {"organization_id": FAKE_ORG_ID}


@pytest.mark.asyncio
async def test_get_org_members_failure(monkeypatch):
    client = FakeAsyncClient({
        "get-organization-members-details": FakeResponse(403, text="Forbidden"),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    with pytest.raises(ValueError, match="Failed to fetch organization members"):
        await supabase_client.get_org_members(FAKE_JWT, FAKE_ORG_ID)


# ---------------------------------------------------------------------------
# fetch_org_release_stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_org_release_stage_happy_path(monkeypatch):
    client = FakeAsyncClient({
        "organization_release_stages": FakeResponse(200, json_data=[
            {"release_stage_id": "rs-1", "release_stages": {"name": "Beta"}},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.fetch_org_release_stage(FAKE_JWT, FAKE_ORG_ID)

    assert result == "beta"


@pytest.mark.asyncio
async def test_fetch_org_release_stage_failure_returns_public(monkeypatch):
    client = FakeAsyncClient({
        "organization_release_stages": FakeResponse(500, text="error"),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.fetch_org_release_stage(FAKE_JWT, FAKE_ORG_ID)

    assert result == "public"


@pytest.mark.asyncio
async def test_fetch_org_release_stage_empty_rows_returns_public(monkeypatch):
    client = FakeAsyncClient({
        "organization_release_stages": FakeResponse(200, json_data=[]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.fetch_org_release_stage(FAKE_JWT, FAKE_ORG_ID)

    assert result == "public"


@pytest.mark.asyncio
async def test_fetch_org_release_stage_unknown_stage_returns_public(monkeypatch):
    client = FakeAsyncClient({
        "organization_release_stages": FakeResponse(200, json_data=[
            {"release_stage_id": "rs-1", "release_stages": {"name": "alpha"}},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.fetch_org_release_stage(FAKE_JWT, FAKE_ORG_ID)

    assert result == "public"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_name, expected",
    [
        ("Internal", "internal"),
        ("Early Access", "early_access"),
        ("early-access", "early_access"),
        (" Beta ", "beta"),
        ("PUBLIC", "public"),
    ],
)
async def test_fetch_org_release_stage_normalizes_name(monkeypatch, raw_name, expected):
    client = FakeAsyncClient({
        "organization_release_stages": FakeResponse(200, json_data=[
            {"release_stage_id": "rs-1", "release_stages": {"name": raw_name}},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.fetch_org_release_stage(FAKE_JWT, FAKE_ORG_ID)

    assert result == expected


@pytest.mark.asyncio
async def test_fetch_org_release_stage_missing_nested_key_returns_public(monkeypatch):
    client = FakeAsyncClient({
        "organization_release_stages": FakeResponse(200, json_data=[
            {"release_stage_id": "rs-1", "release_stages": {}},
        ]),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.fetch_org_release_stage(FAKE_JWT, FAKE_ORG_ID)

    assert result == "public"


# ---------------------------------------------------------------------------
# invite_member
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_member_happy_path(monkeypatch):
    client = FakeAsyncClient({
        "invite-member": FakeResponse(200, json_data={"status": "invited"}),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.invite_member(FAKE_JWT, FAKE_ORG_ID, "bob@example.com", "member")

    assert result == {"status": "invited"}
    req = client.requests[0]
    assert req["json"] == {"organization_id": FAKE_ORG_ID, "email": "bob@example.com", "role": "member"}


@pytest.mark.asyncio
async def test_invite_member_failure_returns_error(monkeypatch):
    client = FakeAsyncClient({
        "invite-member": FakeResponse(422, text="Invalid email"),
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

    result = await supabase_client.invite_member(FAKE_JWT, FAKE_ORG_ID, "bad", "member")

    assert "error" in result
    assert "422" in result["error"]


# ---------------------------------------------------------------------------
# _headers helper
# ---------------------------------------------------------------------------


def test_headers_include_apikey_and_bearer():
    headers = supabase_client._headers("my-token")

    assert headers["apikey"] == "fake-anon-key"
    assert headers["Authorization"] == "Bearer my-token"
    assert headers["Content-Type"] == "application/json"
