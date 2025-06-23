import contextvars
from typing import Optional

project_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("project_id", default=None)
organization_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("organization_id", default=None)
organization_llm_providers_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "organization_llm_providers", default=None
)


def set_project_id(project_id: str):
    project_id_var.set(project_id)


def get_project_id() -> Optional[str]:
    return project_id_var.get()


def set_organization_id(organization_id: str):
    organization_id_var.set(organization_id)


def get_organization_id() -> Optional[str]:
    return organization_id_var.get()


def set_organization_llm_providers(organization_llm_providers: list[str]):
    organization_llm_providers_var.set(organization_llm_providers)


def get_organization_llm_providers() -> Optional[list[str]]:
    return organization_llm_providers_var.get()
