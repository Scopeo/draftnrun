import json
import logging
from uuid import UUID

import pandas as pd

from ada_backend.schemas.monitor_schema import OccurenceQuestionsList
from engine.components.types import AgentPayload
from engine.llm_services.llm_service import CompletionService
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import DBColumn, DBDefinition
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

PROMPT = (
    "This is a list of the questions that have been asked as part of "
    "the project and the number of times they have been asked\n"
    "Regroup similar questions into a single general question\n"
    "{questions_list}\n"
    "You must update this list with the question: "
    "{question}"
)

question_table_definition = DBDefinition(
    columns=[
        DBColumn(name="project_id", type="TEXT", is_primary=True, is_nullable=False),
        DBColumn(name="questions", type="TEXT"),
    ]
)


async def get_previous_questions(
    db_service: DBService, project_id: UUID, table_name: str
) -> OccurenceQuestionsList | None:
    try:
        df = db_service.run_query(f"SELECT questions FROM {table_name} WHERE project_id = '{str(project_id)}'")
        if df.empty:
            return None
        else:
            return df["questions"].values[0]
    except Exception as e:
        LOGGER.error(f"Error getting previous questions: {e}")
        return None


async def monitor_questions(db_service: DBService, project_id: UUID, agent_input: dict):
    try:
        agent_input = AgentPayload(**agent_input)
    except Exception as e:
        LOGGER.error(f"Failed to parse agent input {agent_input}: error {e}")
        return
    trace_manager = TraceManager(project_name="ada_backend")
    llm_service = CompletionService(
        provider="openai",
        model_name="gpt-4.1-mini",
        trace_manager=trace_manager,
        temperature=0.5,
    )
    table_name = "questions_occurences"

    previous_questions = await get_previous_questions(db_service, project_id, table_name)
    query = PROMPT.format(questions_list=previous_questions, question=agent_input.last_message.content)

    answer = await llm_service.constrained_complete_with_pydantic_async(
        messages=query, response_format=OccurenceQuestionsList
    )

    new_questions_list = json.dumps(answer.model_dump())
    df = pd.DataFrame(data=[{"project_id": str(project_id)}])
    df["questions"] = str(new_questions_list)
    db_service.create_table(table_name=table_name, table_definition=question_table_definition)

    db_service.upsert_value(
        table_name,
        id_column_name="project_id",
        id=str(project_id),
        values={"questions": str(new_questions_list)},
    )
