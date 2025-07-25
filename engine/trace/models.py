from enum import Enum
from typing import Type

from sqlalchemy import Text, Column, Integer, String, TIMESTAMP, Enum as SQLAlchemyEnum
from sqlalchemy.orm import declarative_base, mapped_column
from opentelemetry.trace.status import StatusCode
from openinference.semconv.trace import OpenInferenceSpanKindValues


# PostgreSQL-compatible enum helper (adapted from ada_backend pattern)
def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re

    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def make_pg_string_enum(enum_cls: Type[Enum]) -> SQLAlchemyEnum:
    """Create PostgreSQL-compatible enum for string-based enums only."""
    return SQLAlchemyEnum(
        enum_cls,
        name=camel_to_snake(enum_cls.__name__),
        values_callable=lambda x: [e.value for e in x],
        native_enum=True,
    )


Base = declarative_base()


class Span(Base):
    __tablename__ = "spans"

    id = Column(Integer, primary_key=True, autoincrement=True)

    trace_rowid = Column(String, nullable=False, index=True)

    span_id = Column(String, nullable=False, unique=True)
    parent_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    span_kind = mapped_column(make_pg_string_enum(OpenInferenceSpanKindValues), nullable=False)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    end_time = Column(TIMESTAMP(timezone=True), nullable=False)

    attributes = Column(Text, nullable=False)
    events = Column(Text, nullable=False)

    status_code = mapped_column(
        SQLAlchemyEnum(StatusCode),
        nullable=False,
        default="UNSET",
        server_default="UNSET",
    )

    status_message = Column(String, nullable=True)
    cumulative_error_count = Column(Integer, nullable=False)
    cumulative_llm_token_count_prompt = Column(Integer, nullable=False)
    cumulative_llm_token_count_completion = Column(Integer, nullable=False)
    llm_token_count_prompt = Column(Integer, nullable=True)
    llm_token_count_completion = Column(Integer, nullable=True)


class OrganizationUsage(Base):
    __tablename__ = "organization_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(String, nullable=False, index=True)
    total_tokens = Column(Integer, nullable=False, default=0)
