from sqlalchemy.orm import mapped_column
from sqlalchemy import (
    String,
    Text,
    Integer,
    Enum as SQLAlchemyEnum,
    UUID,
    TIMESTAMP,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
from opentelemetry.trace.status import StatusCode
from openinference.semconv.trace import OpenInferenceSpanKindValues

from ada_backend.database.models import Base, CallType, EnvType, make_pg_enum


class Span(Base):
    """Represents a trace span in the traces schema."""

    __tablename__ = "spans"
    __table_args__ = {"schema": "traces"}

    id = mapped_column(Integer, primary_key=True, autoincrement=True)

    trace_rowid = mapped_column(String, nullable=False, index=True)

    span_id = mapped_column(String, nullable=False, unique=True)
    parent_id = mapped_column(String, nullable=True, index=True)
    graph_runner_id = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    name = mapped_column(String, nullable=False)
    span_kind = mapped_column(make_pg_enum(OpenInferenceSpanKindValues, schema="traces"), nullable=False)
    start_time = mapped_column(TIMESTAMP(timezone=True), nullable=False, index=True)
    end_time = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    attributes = mapped_column(JSONB, nullable=False)
    events = mapped_column(Text, nullable=False)

    status_code = mapped_column(
        SQLAlchemyEnum(StatusCode, name="statuscode", schema="traces", native_enum=True),
        nullable=False,
        default=StatusCode.UNSET,
        server_default="UNSET",
    )

    status_message = mapped_column(String, nullable=True)
    cumulative_error_count = mapped_column(Integer, nullable=False)
    cumulative_llm_token_count_prompt = mapped_column(Integer, nullable=False)
    cumulative_llm_token_count_completion = mapped_column(Integer, nullable=False)
    llm_token_count_prompt = mapped_column(Integer, nullable=True)
    llm_token_count_completion = mapped_column(Integer, nullable=True)
    environment = mapped_column(make_pg_enum(EnvType), nullable=True)
    call_type = mapped_column(make_pg_enum(CallType), nullable=True)
    project_id = mapped_column(String, nullable=True, index=True)
    tag_name = mapped_column(String, nullable=True)
    component_instance_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("component_instances.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def __str__(self):
        return f"Span(span_id={self.span_id}, name={self.name})"


class SpanMessage(Base):
    """Represents span messages in the traces schema."""

    __tablename__ = "span_messages"
    __table_args__ = {"schema": "traces"}

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    span_id = mapped_column(String, ForeignKey("traces.spans.span_id", ondelete="CASCADE"), nullable=False)
    input_content = mapped_column(Text, nullable=False)
    output_content = mapped_column(Text, nullable=False)

    def __str__(self):
        return f"SpanMessage(span_id={self.span_id})"
