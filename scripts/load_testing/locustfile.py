"""FastAPI Load Testing with Locust"""

import json
import random
from locust import HttpUser, task, between
from scripts.load_testing.utils.auth_helpers import get_test_jwt_token, TEST_ORGANIZATION_ID, TEST_PROJECT_ID
from scripts.load_testing.utils.data_generators import generate_chat_message, generate_project_data


class BasicEndpointsUser(HttpUser):
    """Basic endpoints without authentication - perfect for demo"""

    wait_time = between(1, 3)
    weight = 3  # 75% of traffic in mixed mode

    @task(5)
    def get_root(self):
        """GET / - Welcome message"""
        self.client.get("/")

    @task(3)
    def get_docs(self):
        """GET /docs - Swagger documentation"""
        self.client.get("/docs")

    @task(2)
    def get_openapi(self):
        """GET /openapi.json - OpenAPI spec"""
        self.client.get("/openapi.json")

    @task(1)
    def get_metrics(self):
        """GET /metrics - Prometheus metrics endpoint"""
        self.client.get("/metrics")


class AuthenticatedUser(HttpUser):
    """
    Scenario 2: Authenticated endpoints
    More realistic testing with actual API usage
    """

    wait_time = between(2, 5)
    weight = 1  # 25% of traffic in mixed mode

    def on_start(self):
        """Setup authentication token"""
        try:
            self.token = get_test_jwt_token()
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.org_id = TEST_ORGANIZATION_ID
            self.project_id = TEST_PROJECT_ID
        except Exception as e:
            print(f"Auth setup failed: {e}")
            self.token = None
            self.headers = {}

    @task(4)
    def get_projects_by_org(self):
        """GET /projects/org/{organization_id}"""
        if not self.token:
            return

        self.client.get(f"/projects/org/{self.org_id}", headers=self.headers, name="/projects/org/[org_id]")

    @task(3)
    def get_project_details(self):
        """GET /projects/{project_id}"""
        if not self.token:
            return

        self.client.get(f"/projects/{self.project_id}", headers=self.headers, name="/projects/[project_id]")

    @task(2)
    def get_components(self):
        """GET /components/{organization_id}"""
        if not self.token:
            return

        self.client.get(f"/components/{self.org_id}", headers=self.headers, name="/components/[org_id]")

    @task(2)
    def get_sources(self):
        """GET /sources/{organization_id}"""
        if not self.token:
            return

        self.client.get(f"/sources/{self.org_id}", headers=self.headers, name="/sources/[org_id]")

    @task(1)
    def get_project_charts(self):
        """GET /projects/{project_id}/charts"""
        if not self.token:
            return

        duration = random.choice([1, 7, 30])  # 1 hour, 7 days, 30 days
        self.client.get(
            f"/projects/{self.project_id}/charts?duration={duration}",
            headers=self.headers,
            name="/projects/[project_id]/charts",
        )

    @task(1)
    def get_project_trace(self):
        """GET /projects/{project_id}/trace"""
        if not self.token:
            return

        duration = random.choice([1, 7])  # 1 hour, 7 days
        self.client.get(
            f"/projects/{self.project_id}/trace?duration={duration}",
            headers=self.headers,
            name="/projects/[project_id]/trace",
        )


class HeavyLoadUser(HttpUser):
    """Heavy endpoints that could stress the system - use sparingly"""

    wait_time = between(5, 10)
    weight = 0  # Disabled by default

    def on_start(self):
        """Setup authentication token"""
        try:
            self.token = get_test_jwt_token()
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.org_id = TEST_ORGANIZATION_ID
            self.project_id = TEST_PROJECT_ID
        except Exception as e:
            print(f"Auth setup failed: {e}")
            self.token = None
            self.headers = {}

    @task(1)
    def chat_with_agent(self):
        """POST /projects/{project_id}/draft/chat - Heavy LLM call"""
        if not self.token:
            return

        chat_data = generate_chat_message()

        with self.client.post(
            f"/projects/{self.project_id}/draft/chat",
            headers=self.headers,
            json=chat_data,
            name="/projects/[project_id]/draft/chat",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 422:
                # Expected for some test data
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


# For demo purposes, you can run individual scenarios:
# locust -f locustfile.py BasicEndpointsUser --host=http://localhost:8000
# locust -f locustfile.py AuthenticatedUser --host=http://localhost:8000
# locust -f locustfile.py HeavyLoadUser --host=http://localhost:8000
