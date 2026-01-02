import logging
from pathlib import Path
from typing import Optional

from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import CompletionService
from engine.storage_service.db_service import DBService
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

CREDENTIAL_PATH = Path("data_ingestion", "sql", "sql_credentials.env")
JSON_SCHEMA_PATH = Path("data_ingestion", "sql", "sql_table_schema.json")

SIMILARITY_TOP_K = 3

INPUT_TABLES = None
CONFIG_SQL_QUERY_ENGINE = {
    "credentials_path": CREDENTIAL_PATH,
    "json_schema_path": JSON_SCHEMA_PATH,
    "similarity_top_k": SIMILARITY_TOP_K,
    "input_tables": INPUT_TABLES,
}

TEXT_TO_SQL_PROMPT = (
    "Given an input question, create a syntactically correct {dialect} "
    "query to run on the database. "
    "If you use %, just make it double %%.\n"
    "Strings are always compared in lower case. \n"
    "Never query for all the columns from a specific table, only ask for a "
    "few relevant columns given the question.\n\n"
    "Pay attention to use only the column names that you can see in the schema "
    "description. "
    "Be careful to not query for columns that do not exist. "
    "Pay attention to which column is in which table. "
    "Also, qualify column names with the table name when needed. "
    "Only answer with the SQL Query to run. "
    "Do not include any additional information in the answer (no code block)\n"
    "Only use tables listed below.\n"
    "{schema}\n\n"
    "Question: {query_str}\n"
    "SQLQuery: "
)

SYNTHESIZE_SQL_PROMPT = (
    "Given an input question, synthesize a response from the query results."
    "Query: {query_str}\n"
    "SQL: {sql_query}\n"
    "SQL Response: {sql_answer}\n"
    "Response: "
)

DEFAULT_SQL_TOOL_DESCRIPTION = ToolDescription(
    name="SQL_Tool",
    description=(
        "Generate and execute an SQL query based on a user natural language query."
        "This tool has access to database schema and doesn't need user to provide it."
    ),
    tool_properties={
        "natural_language_query": {
            "type": "string",
            "description": (
                "The user's natural language query to interrogate the database. "
                "For example: 'What are the top 5 most expensive products?'\n"
                "Don't put SQL queries here, only natural language queries."
            ),
        },
    },
    required_tool_properties=["natural_language_query"],
)


class SQLTool(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        completion_service: CompletionService,
        db_service: DBService,
        component_attributes: ComponentAttributes,
        include_tables: Optional[list[str]] = None,
        additional_db_description: Optional[str] = None,
        tool_description: Optional[ToolDescription] = DEFAULT_SQL_TOOL_DESCRIPTION,
        text_to_sql_prompt: str = TEXT_TO_SQL_PROMPT,
        synthesize: bool = False,
        synthesize_sql_prompt: str = SYNTHESIZE_SQL_PROMPT,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._db_service = db_service
        self._include_tables = include_tables
        self._additional_db_description = additional_db_description
        self._completion_service = completion_service
        self._text_to_sql_prompt = text_to_sql_prompt
        self._synthesize = synthesize
        self._dialect = db_service.engine.dialect.name
        self.synthesize_sql_prompt = synthesize_sql_prompt

    async def _run_without_io_trace(
        self, *inputs: AgentPayload, natural_language_query: Optional[str] = None, ctx: Optional[dict] = None
    ) -> AgentPayload:
        agent_input = inputs[0]
        query_str = natural_language_query or agent_input.last_message.content
        schema = self._db_service.get_db_description(self._include_tables)
        if self._additional_db_description:
            schema += self._additional_db_description
        input_prompt = self._text_to_sql_prompt.format(query_str=query_str, schema=schema, dialect=self._dialect)
        generate_sql_query = await self._completion_service.complete_async(
            messages=[{"role": "user", "content": input_prompt}]
        )

        sql_query = generate_sql_query
        sql_output = self._db_service.run_query(sql_query).to_markdown(index=False)
        output_message = sql_output

        if self._synthesize:
            synthetize_prompt = self.synthesize_sql_prompt.format(
                query_str=query_str, sql_query=sql_query, sql_answer=sql_output
            )
            synthetize_answer = await self._completion_service.complete_async(
                messages=[{"role": "assistant", "content": synthetize_prompt}]
            )
            output_message = synthetize_answer

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=output_message)],
            artifacts={"input_question": query_str, "sql_query": sql_query, "sql_output": sql_output},
        )
