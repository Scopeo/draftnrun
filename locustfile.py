import random

from locust import HttpUser, task, between

from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings


class LoadTestUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.organization_id = "37b7d67f-8f29-4fce-8085-19dea582f605"
        self.project_id = "f7ddbfcb-6843-4ae9-a15b-40aa565b955b"
        self.env = "production"
        JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
        self.headers = {
            "Authorization": f"Bearer {JWT_TOKEN}",
        }

    @task
    def get_project_trace(self):
        duration = random.choice([60, 300, 900])
        self.client.get(f"/projects/{self.project_id}/trace?duration={duration}", headers=self.headers)

    @task
    def get_project_info(self):
        self.client.get(f"/projects/{self.project_id}", headers=self.headers)

    @task
    def post_run_agent(self):
        data = {"messages": [{"role": "user", "content": "Bonjour, comment vas-tu ?"}]}
        self.client.post(f"/projects/{self.project_id}/{self.env}/run", json=data, headers=self.headers)
