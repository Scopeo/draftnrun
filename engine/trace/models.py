from sqlalchemy import Text, Column, Integer, String, TIMESTAMP, Enum
from sqlalchemy.orm import declarative_base
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

TRACES_DB_URL = "sqlite:///engine/trace/traces.db"

Base = declarative_base()


class Span(Base):
    __tablename__ = "spans"

    id = Column(Integer, primary_key=True, autoincrement=True)

    trace_rowid = Column(String, nullable=False, index=True)

    span_id = Column(String, nullable=False, unique=True)
    parent_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    span_kind = Column(Enum(SpanKind), nullable=False)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    end_time = Column(TIMESTAMP(timezone=True), nullable=False)

    attributes = Column(Text, nullable=False)
    events = Column(Text, nullable=False)

    status_code = Column(
        Enum(StatusCode),
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
