"""FastAPI Load Testing with Locust"""

from locust import HttpUser, between, task


class BasicEndpointsUser(HttpUser):
    """Basic endpoints load testing - perfect for demos and performance validation"""

    wait_time = between(1, 3)

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


# Manual testing:
# locust -f locustfile.py BasicEndpointsUser --host=http://localhost:8000
