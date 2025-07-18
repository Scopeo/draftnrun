from sqlalchemy import Text, Column, TIMESTAMP, UUID as SQLAlchemyUUID
from sqlalchemy.orm import declarative_base, mapped_column
from sqlalchemy.sql import func


Base = declarative_base()


class QuestionsAnswers(Base):
    __tablename__ = "questions_answers"

    id = mapped_column(SQLAlchemyUUID(as_uuid=True), primary_key=True, index=True, default=func.uuid_generate_v4())

    organization_id = mapped_column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    project_id = mapped_column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    question = Column(Text, nullable=False)
    groundtruth = Column(Text, nullable=False)
