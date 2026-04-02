import logging
from pathlib import Path
from typing import Callable, Optional, Type
from uuid import UUID

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.constants import DEFAULT_MODEL
from engine.llm_services.llm_service import CompletionService
from engine.llm_services.utils import get_llm_provider_and_model
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


class SQLToolInputs(BaseModel):
    completion_model: str = Field(
        default=DEFAULT_MODEL,
        json_schema_extra={
            "is_tool_input": False,
            "parameter_type": ParameterType.LLM_MODEL,
            "ui_component": "Select",
            "ui_component_properties": {"label": "Model Name", "model_capabilities": ["completion"]},
        },
    )
    natural_language_query: str = Field(
        description="The user's natural language query to interrogate the database.",
        json_schema_extra={
            "is_tool_input": True,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Natural Language Query",
                placeholder="What are the top 5 most expensive products?",
                description="A natural language question about the database. Do not put raw SQL here.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class SQLToolOutputs(BaseModel):
    output: str = Field(description="The final response message (raw SQL result or synthesized answer).")
    input_question: str = Field(description="The original natural language query.")
    sql_query: str = Field(description="The generated SQL query.")
    sql_output: str = Field(description="The raw SQL query result in markdown format.")


class SQLTool(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return SQLToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return SQLToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "natural_language_query", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        db_service: DBService,
        component_attributes: ComponentAttributes,
        temperature: float = 1.0,
        llm_api_key: Optional[str] = None,
        model_id_resolver: Optional[Callable[[str], Optional[UUID]]] = None,
        include_tables: Optional[list[str] | str] = None,
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
        self._temperature = temperature
        self._llm_api_key = llm_api_key
        self._model_id_resolver = model_id_resolver or (lambda _: None)
        self._include_tables = self._parse_include_tables(include_tables)
        self._additional_db_description = additional_db_description
        self._text_to_sql_prompt = text_to_sql_prompt
        self._synthesize = synthesize
        self._dialect = db_service.engine.dialect.name
        self.synthesize_sql_prompt = synthesize_sql_prompt

    @staticmethod
    def _parse_include_tables(value: Optional[list[str] | str]) -> Optional[list[str]]:
        if value is None or isinstance(value, list):
            return value or None
        tables = [t.strip() for t in value.replace(",", " ").split() if t.strip()]
        return tables or None

    def _build_completion_service(self, completion_model: str) -> CompletionService:
        provider, model_name = get_llm_provider_and_model(completion_model)
        return CompletionService(
            provider=provider,
            model_name=model_name,
            trace_manager=self.trace_manager,
            temperature=self._temperature,
            api_key=self._llm_api_key,
            model_id=self._model_id_resolver(model_name),
        )

    async def _run_without_io_trace(
        self,
        inputs: SQLToolInputs,
        ctx: Optional[dict] = None,
    ) -> SQLToolOutputs:
        completion_service = self._build_completion_service(inputs.completion_model)
        query_str = inputs.natural_language_query
        schema = self._db_service.get_db_description(table_names=self._include_tables)
        if self._additional_db_description:
            schema += self._additional_db_description
        input_prompt = self._text_to_sql_prompt.format(query_str=query_str, schema=schema, dialect=self._dialect)
        generate_sql_query = await completion_service.complete_async(
            messages=[{"role": "user", "content": input_prompt}]
        )

        sql_query = generate_sql_query
        sql_output = self._db_service.run_query(sql_query).to_markdown(index=False)
        output_message = sql_output

        if self._synthesize:
            synthetize_prompt = self.synthesize_sql_prompt.format(
                query_str=query_str, sql_query=sql_query, sql_answer=sql_output
            )
            synthetize_answer = await completion_service.complete_async(
                messages=[{"role": "assistant", "content": synthetize_prompt}]
            )
            output_message = synthetize_answer

        return SQLToolOutputs(
            output=output_message,
            input_question=query_str,
            sql_query=sql_query,
            sql_output=sql_output,
        )
