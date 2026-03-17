#!/usr/bin/env python3
"""
Creates a simple test project with Start → AI (LLM Call) workflow for memory profiling.
Outputs the project ID and API key needed for the memory test script.
"""

import json
import sys
import uuid

import requests

SUPABASE_URL = "https://pjnpfnqwglwxvpaookdh.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBqbnBmbnF3Z2x3eHZwYW9va2RoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzg1ODE5MzUsImV4cCI6MjA1NDE1NzkzNX0."
    "hO5Gz38tHRh1FAWebVq8MMFrwotpRVLfHGyUBNQM0so"
)
BASE_URL = "http://localhost:8000"
ORG_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"

# Component UUIDs from seed data
START_COMPONENT_ID = "01357c0b-bc99-44ce-a435-995acc5e2544"
START_VERSION_ID = "7a6e2c9b-5b1b-4a9b-9f2f-9b7f0540d4b0"
LLM_CALL_COMPONENT_ID = "7a039611-49b3-4bfd-b09b-c0f93edf3b79"
LLM_CALL_VERSION_ID = "7a039611-49b3-4bfd-b09b-c0f93edf3b79"


def get_supabase_token(email: str, password: str) -> str:
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main():
    print("Getting Supabase token...")
    token = get_supabase_token("mel@scopeo.ai", "fatkuz-taCqi1-qyhdum")
    jwt_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1. Create project
    project_id = str(uuid.uuid4())
    print(f"Creating project {project_id}...")
    resp = requests.post(
        f"{BASE_URL}/projects/{ORG_ID}",
        headers=jwt_headers,
        json={
            "project_id": project_id,
            "project_name": "Memory Profile Test",
            "description": "Simple LLM call for memory profiling",
        },
    )
    if resp.status_code != 200:
        print(f"Failed to create project: {resp.status_code} {resp.text}")
        sys.exit(1)
    project_data = resp.json()
    graph_runner_id = project_data["graph_runners"][0]["graph_runner_id"]
    print(f"  Project created. Draft graph runner: {graph_runner_id}")

    # 2. Update graph with Start → LLM Call
    start_node_id = str(uuid.uuid4())
    llm_node_id = str(uuid.uuid4())
    edge_id = str(uuid.uuid4())

    graph_update = {
        "component_instances": [
            {
                "id": start_node_id,
                "name": "Start",
                "ref": "Start",
                "is_start_node": True,
                "component_id": START_COMPONENT_ID,
                "component_version_id": START_VERSION_ID,
                "parameters": [],
                "input_port_instances": [],
            },
            {
                "id": llm_node_id,
                "name": "LLM Call",
                "ref": "LLM Call",
                "is_start_node": False,
                "component_id": LLM_CALL_COMPONENT_ID,
                "component_version_id": LLM_CALL_VERSION_ID,
                "parameters": [
                    {
                        "name": "completion_model",
                        "value": "openai:gpt-4.1-mini",
                    },
                    {
                        "name": "default_temperature",
                        "value": 0.7,
                    },
                ],
                "input_port_instances": [],
            },
        ],
        "relationships": [],
        "edges": [
            {
                "id": edge_id,
                "origin": start_node_id,
                "destination": llm_node_id,
            },
        ],
        "port_mappings": [],
    }

    print("Updating graph...")
    resp = requests.put(
        f"{BASE_URL}/projects/{project_id}/graph/{graph_runner_id}",
        headers=jwt_headers,
        json=graph_update,
    )
    if resp.status_code != 200:
        print(f"Failed to update graph: {resp.status_code} {resp.text}")
        sys.exit(1)
    print("  Graph updated.")

    # 3. Deploy to production
    print("Deploying to production...")
    resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/graph/{graph_runner_id}/deploy",
        headers=jwt_headers,
    )
    if resp.status_code != 200:
        print(f"Failed to deploy: {resp.status_code} {resp.text}")
        sys.exit(1)
    deploy_data = resp.json()
    print(f"  Deployed. Prod graph runner: {deploy_data['prod_graph_runner_id']}")

    # 4. Get API key
    api_key = "taylor_1OLDy02vqeToKK2wo0Aak0Rmzgwbcn8m"

    # 5. Test a run
    print("\nTesting run...")
    resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/production/run",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json={"messages": [{"role": "user", "content": "Say hello in exactly 3 words."}]},
        timeout=120,
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"  Response: {json.dumps(result, indent=2)[:500]}")
    else:
        print(f"  Error: {resp.text[:500]}")

    print(f"\n{'='*60}")
    print(f"Project ID:    {project_id}")
    print(f"Environment:   production")
    print(f"API Key:       {api_key}")
    print(f"\nRun memory test with:")
    print(f"  uv run python scripts/memory_profiling/run_memory_test.py \\")
    print(f"    --api-key {api_key} \\")
    print(f"    --project-id {project_id} \\")
    print(f"    --environment production \\")
    print(f"    --iterations 10")


if __name__ == "__main__":
    main()
