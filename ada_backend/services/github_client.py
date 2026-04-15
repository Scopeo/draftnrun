import logging
import time

import httpx
import jwt

from settings import settings

LOGGER = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GithubClientError(Exception):
    pass


TIMEOUT = 30


def _make_app_jwt() -> str:
    """Create a short-lived JWT signed with the GitHub App's private key."""
    if not settings.GITHUB_APP_ID:
        raise RuntimeError("GITHUB_APP_ID is not configured — cannot authenticate as a GitHub App")
    if not settings.GITHUB_APP_PRIVATE_KEY:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY is not configured — cannot authenticate as a GitHub App")
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": settings.GITHUB_APP_ID,
    }
    return jwt.encode(payload, settings.GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_installation_token(installation_id: int) -> str:
    """Exchange the App JWT for a short-lived installation access token (valid ~1 hour)."""
    app_jwt = _make_app_jwt()
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, headers=_headers(app_jwt))
            resp.raise_for_status()
            return resp.json()["token"]
    except httpx.HTTPStatusError as err:
        body = err.response.text[:200]
        raise GithubClientError(
            f"GitHub token exchange failed for installation {installation_id}: "
            f"HTTP {err.response.status_code} — {body}"
        ) from err
    except httpx.RequestError as err:
        raise GithubClientError(
            f"GitHub token exchange request failed for installation {installation_id}: {err}"
        ) from err


async def fetch_file(repo: str, path: str, ref: str, installation_id: int) -> str:
    """Fetch raw file content from a GitHub repo at a given commit ref."""
    token = await get_installation_token(installation_id)
    headers = _headers(token)
    headers["Accept"] = "application/vnd.github.raw+json"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}",
            params={"ref": ref},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.text


async def get_branch_head_sha(repo: str, branch: str, installation_id: int) -> str:
    """Return the HEAD commit SHA for a branch."""
    token = await get_installation_token(installation_id)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/commits/{branch}",
            headers=_headers(token),
        )
        resp.raise_for_status()
        return resp.json()["sha"]


async def list_installation_repos(installation_id: int) -> list[dict]:
    """List repositories accessible to a GitHub App installation."""
    # TODO: token can expire mid-pagination — refresh via get_installation_token(installation_id)
    #  on 401/403 and retry the failed page once before raising.
    token = await get_installation_token(installation_id)
    repos: list[dict] = []
    url = f"{GITHUB_API_BASE}/installation/repositories"
    params: dict = {"per_page": 100}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while url:
            resp = await client.get(url, params=params, headers=_headers(token))
            resp.raise_for_status()
            repos.extend(resp.json().get("repositories", []))
            url = resp.links.get("next", {}).get("url")
            params = {}
    return repos


async def list_repo_contents(repo: str, path: str, ref: str, installation_id: int) -> list[dict]:
    """List directory contents in a GitHub repo (for folder picker)."""
    token = await get_installation_token(installation_id)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}",
            params={"ref": ref},
            headers=_headers(token),
        )
        resp.raise_for_status()
        return resp.json()


async def find_graph_json_folders(repo: str, ref: str, installation_id: int) -> list[str]:
    """Return folder paths (relative to repo root) that contain a graph.json file.

    Uses the Git Trees API with recursive mode for a single-call scan.
    Returns empty string "" for root-level graph.json, or "subfolder/path" otherwise.
    """
    token = await get_installation_token(installation_id)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/git/trees/{ref}",
            params={"recursive": "1"},
            headers=_headers(token),
        )
        resp.raise_for_status()

    folders: list[str] = []
    for item in resp.json().get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if path == "graph.json":
            folders.append("")
        elif path.endswith("/graph.json"):
            folders.append(path.rsplit("/graph.json", 1)[0])
    return folders
