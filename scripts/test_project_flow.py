"""
E2E test: save-version -> deploy -> run for a list of projects.

Authenticates against Supabase with a real test user, then hits the standard
API endpoints with the resulting JWT. No backend code changes required.

The project list is read from the PROJECT_TEST_MATRIX env var, expected as JSON:
[
  {"project_id": "<uuid>", "input": {"messages": [{"role": "user", "content": "Hello"}]}},
  ...
]

Required env vars:
  PROJECT_TEST_MATRIX   – JSON array (see above)
  STAGING_BASE_URL      – Backend base URL (e.g. https://staging.example.com)
  SUPABASE_URL          – Supabase project URL (e.g. https://xyz.supabase.co)
  SUPABASE_ANON_KEY     – Supabase anon/public key
  E2E_USER_EMAIL        – Test user email
  E2E_USER_PASSWORD     – Test user password
"""

import json
import os
from typing import Any

import pytest
import requests

# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


_REQUIRED_ENTRY_KEYS = {"project_id", "input"}


def _load_project_matrix() -> list[dict[str, Any]]:
    raw = _require_env("PROJECT_TEST_MATRIX")
    matrix = json.loads(raw)
    if not isinstance(matrix, list) or len(matrix) == 0:
        raise ValueError("PROJECT_TEST_MATRIX must be a non-empty JSON array")
    for entry in matrix:
        missing = _REQUIRED_ENTRY_KEYS - entry.keys()
        if missing:
            raise ValueError(f"Matrix entry missing keys {missing}. Each entry needs: {_REQUIRED_ENTRY_KEYS}")
    return matrix


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:
    return _require_env("STAGING_BASE_URL").rstrip("/")


@pytest.fixture(scope="session")
def auth_headers() -> dict[str, str]:
    """Authenticate against Supabase and return a Bearer header with a real JWT."""
    supabase_url = _require_env("SUPABASE_URL").rstrip("/")
    anon_key = _require_env("SUPABASE_ANON_KEY")
    email = _require_env("E2E_USER_EMAIL")
    password = _require_env("E2E_USER_PASSWORD")

    resp = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Per-project parametrization
# ---------------------------------------------------------------------------


def _matrix_ids() -> list[str]:
    try:
        matrix = _load_project_matrix()
    except Exception:
        return ["matrix-load-error"]
    return [entry["project_id"] for entry in matrix]


def _matrix_params() -> list[dict[str, Any]]:
    try:
        return _load_project_matrix()
    except Exception:
        return [{}]


@pytest.fixture(params=_matrix_params(), ids=_matrix_ids(), scope="class")
def project_entry(request) -> dict[str, Any]:
    """Yields one {project_id, input} entry from the matrix."""
    return request.param


# ---------------------------------------------------------------------------
# Helper: resolve draft graph_runner_id
# ---------------------------------------------------------------------------


def _get_draft_graph_runner_id(base_url: str, project_id: str, headers: dict[str, str]) -> str:
    resp = requests.get(
        f"{base_url}/projects/{project_id}",
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    for gr in data.get("graph_runners", []):
        if gr.get("env") == "draft":
            return gr["graph_runner_id"]

    raise RuntimeError(
        f"No draft graph runner found for project {project_id}. Available: {data.get('graph_runners', [])}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProjectFlow:
    """Save-version, deploy, and run for each project in the matrix."""

    def test_save_version(self, base_url, auth_headers, project_entry):
        project_id = project_entry["project_id"]
        graph_runner_id = _get_draft_graph_runner_id(base_url, project_id, auth_headers)

        resp = requests.post(
            f"{base_url}/projects/{project_id}/graph/{graph_runner_id}/save-version",
            headers=auth_headers,
            timeout=60,
        )
        resp.raise_for_status()

        body = resp.json()
        assert "saved_graph_runner_id" in body
        assert "tag_version" in body

    def test_deploy(self, base_url, auth_headers, project_entry):
        project_id = project_entry["project_id"]
        graph_runner_id = _get_draft_graph_runner_id(base_url, project_id, auth_headers)

        resp = requests.post(
            f"{base_url}/projects/{project_id}/graph/{graph_runner_id}/deploy",
            headers=auth_headers,
            timeout=60,
        )
        resp.raise_for_status()

        body = resp.json()
        assert "prod_graph_runner_id" in body
        assert "draft_graph_runner_id" in body

    def test_run(self, base_url, auth_headers, project_entry):
        project_id = project_entry["project_id"]
        input_data = project_entry["input"]

        resp = requests.post(
            f"{base_url}/projects/{project_id}/production/chat",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=input_data,
            timeout=120,
        )
        resp.raise_for_status()

        body = resp.json()
        assert "message" in body, f"Response missing 'message' field: {body}"
        assert body.get("error") is None, f"Run returned an error: {body['error']}"
