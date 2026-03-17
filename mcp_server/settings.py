from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "credentials.env"), extra="ignore")

    SUPABASE_PROJECT_URL: str
    SUPABASE_PROJECT_KEY: str
    MCP_BASE_URL: str = "http://localhost:8090"
    BACKEND_URL: str = "http://ada-api"
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    MCP_REQUEST_TIMEOUT: int = 30
    MCP_RESPONSE_MAX_SIZE: int = 50_000
    MCP_ORG_SESSION_TTL: int = 86400

    REDIS_URL: Optional[str] = None
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None

    @property
    def redis_url(self) -> str:
        """Build Redis URL from REDIS_URL or individual REDIS_HOST/PORT/PASSWORD vars.

        Matches the env var convention used by the rest of the stack (K8s secrets
        provide REDIS_HOST, REDIS_PORT, REDIS_PASSWORD — not REDIS_URL).
        """
        if self.REDIS_URL:
            return self.REDIS_URL
        host = self.REDIS_HOST or "localhost"
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{host}:{self.REDIS_PORT}"
        return f"redis://{host}:{self.REDIS_PORT}"


settings = MCPSettings()
