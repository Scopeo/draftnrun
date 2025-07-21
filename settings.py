import os
import re
import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from pydantic import model_validator, ValidationError
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent.resolve()
CHATBOT_CONFIG_TEMPLATE_VARS = {
    "base_dir": str(BASE_DIR),
}
CUSTOM_MODELS_JSON_PATH = BASE_DIR / "custom_models.json"


def load_yaml(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        raise FileNotFoundError(f"YAML file not found: {file_path}")
    with open(file_path, "r") as file:
        content = file.read()

    def replace_template_vars(match: re.Match) -> str:
        var_name = match.group(1)
        if not var_name:
            return match.group(0)
        if var_name not in CHATBOT_CONFIG_TEMPLATE_VARS:
            raise ValueError(f"Unknown template variable: {var_name}")
        return CHATBOT_CONFIG_TEMPLATE_VARS[var_name]

    template_pattern = r"\${([^}]+)}"
    content = re.sub(template_pattern, replace_template_vars, content)
    return yaml.safe_load(content)


class BaseConfig(BaseSettings):
    OPENAI_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_BASE_URL: Optional[str] = None
    CEREBRAS_API_KEY: Optional[str] = None
    CEREBRAS_BASE_URL: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None

    SNOWFLAKE_ACCOUNT: Optional[str] = None
    SNOWFLAKE_USER: Optional[str] = None
    SNOWFLAKE_PASSWORD: Optional[str] = None

    QDRANT_CLUSTER_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None

    TAVILY_API_KEY: Optional[str] = None
    E2B_API_KEY: Optional[str] = None

    @property
    def custom_models(self) -> dict[str, dict[str, Any]]:
        if not CUSTOM_MODELS_JSON_PATH.exists():
            return {}
        with open(CUSTOM_MODELS_JSON_PATH, "r") as file:
            custom_models = json.load(file)
            return custom_models

    FERNET_KEY: Optional[str] = None
    BACKEND_SECRET_KEY: Optional[str] = None
    RELOAD_SCOPEO_AGENTS_BACKEND: bool = False
    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADA_API_KEY: Optional[str] = None

    # Database settings
    ADA_DB_DRIVER: str = "sqlite"
    ADA_DB_HOST: Optional[str] = None
    ADA_DB_PORT: int = 5432
    ADA_DB_USER: Optional[str] = None
    ADA_DB_PASSWORD: Optional[str] = None
    ADA_DB_NAME: Optional[str] = None
    ADA_DB_URL: Optional[str] = None

    # Ingestion database settings
    INGESTION_DB_URL: Optional[str] = None

    # Traces database settings
    TRACES_DB_URL: Optional[str] = None

    SUPABASE_PROJECT_URL: Optional[str] = None
    SUPABASE_PROJECT_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_SECRET_KEY: Optional[str] = None
    CORS_ALLOW_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,*"
    )

    SUPABASE_USERNAME: Optional[str] = None
    SUPABASE_PASSWORD: Optional[str] = None

    SUPABASE_BUCKET_NAME: Optional[str] = None

    TEST_USER_EMAIL: Optional[str] = None
    TEST_USER_PASSWORD: Optional[str] = None

    INGESTION_API_KEY: Optional[str] = None
    INGESTION_API_KEY_HASHED: Optional[str] = None
    ADA_URL: Optional[str] = None

    # Redis configuration
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_QUEUE_NAME: str = "ada_ingestion_queue"

    # S3 configuration
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION_NAME: Optional[str] = None

    # Google OAuth configuration
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # Observability stack endpoints
    TEMPO_ENDPOINT: str = "http://localhost:4318/v1/traces"
    PROMETHEUS_URL: str = "http://localhost:9090"
    GRAFANA_URL: str = "http://localhost:3000"
    GF_SECURITY_ADMIN_USER: Optional[str] = None
    GF_SECURITY_ADMIN_PASSWORD: Optional[str] = None

    # Observability stack feature flag
    ENABLE_OBSERVABILITY_STACK: bool = False

    # Number of pages to detect document type
    NUMBER_OF_PAGES_TO_DETECT_DOCUMENT_TYPE: Optional[int] = 5

    @model_validator(mode="after")
    @classmethod
    def sync_db_settings(cls, values):
        url = values.ADA_DB_URL

        if values.ADA_DB_DRIVER == "sqlite":
            if not url:
                raise ValidationError("ADA_DB_URL is required for SQLite")
            return values

        has_url = bool(url)
        has_components = any([values.ADA_DB_HOST, values.ADA_DB_USER, values.ADA_DB_PASSWORD, values.ADA_DB_NAME])

        if has_url and has_components and values.ADA_DB_DRIVER != "sqlite":
            raise ValidationError("You cannot define ADA_DB_URL and individual components simultaneously")

        if url:
            parsed = urlparse(url)
            if parsed.scheme.startswith("postgresql"):
                values.ADA_DB_DRIVER = "postgresql"
                values.ADA_DB_HOST = parsed.hostname
                values.ADA_DB_PORT = parsed.port or 5432
                values.ADA_DB_USER = parsed.username
                values.ADA_DB_PASSWORD = parsed.password
                values.ADA_DB_NAME = parsed.path.lstrip("/") if parsed.path else None

        elif all(
            [values.ADA_DB_DRIVER, values.ADA_DB_HOST, values.ADA_DB_USER, values.ADA_DB_PASSWORD, values.ADA_DB_NAME]
        ):
            driver = values.ADA_DB_DRIVER
            host = values.ADA_DB_HOST
            port = values.ADA_DB_PORT or 5432
            user = values.ADA_DB_USER
            password = values.ADA_DB_PASSWORD
            name = values.ADA_DB_NAME

            values.ADA_DB_URL = f"{driver}://{user}:{password}@{host}:{port}/{name}"

        return values


class DevSettings(BaseConfig):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / "credentials.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ProdSettings(BaseConfig):
    pass


class TestSettings(BaseConfig):
    pass


def get_settings() -> BaseConfig:
    env = os.getenv("APP_ENV", "dev")
    match env:
        case "dev":
            settings = DevSettings()
        case "prod":
            raise NotImplementedError("Production settings not implemented")
        case "test":
            settings = DevSettings()
        case _:
            raise ValueError("Invalid environment name")

    load_dotenv(
        dotenv_path=settings.model_config.get("env_file"),
        encoding=settings.model_config.get("env_file_encoding"),
        override=True,
    )
    return settings


settings = get_settings()
