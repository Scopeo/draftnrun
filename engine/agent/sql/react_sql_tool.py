from typing import Optional

from engine.agent.agent import ToolDescription
from engine.agent.react_function_calling import ReActAgent
from engine.agent.sql.run_sql_query_tool import RunSQLQueryTool
from engine.llm_services.llm_service import LLMService
from engine.storage_service.db_service import DBService
from engine.trace.trace_manager import TraceManager
from engine.storage_service.snowflake_service.snowflake_service import SnowflakeService


DEFAULT_REACT_SQL_TOOL_DESCRIPTION = ToolDescription(
    name="React_SQL_Tool",
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

DEFAULT_REACT_SQL_TOOL_PROMPT = (
    "{additional_db_description}\n"
    "You have access to a database with the following schema:\n"
    "{schema}\n\n"
    "Answer the question using SQL tool and the information.\n"
    "Anwer should not be the sql query, but the answer to the question.\n"
    "Create a syntactically correct {dialect} query to run on the database.\n"
    "If you use %, just make it double %%.\n"
    "Strings are always compared in lower case. \n"
    "Never query for all the columns from a specific table, only ask for a "
    "few relevant columns given the question.\n\n"
    "Pay attention to use only the column names that you can see in the schema "
    "description. "
    "Be careful to not query for columns that do not exist. "
    "Pay attention to which column is in which table. "
    "Also, qualify column names with the table name when needed. "
    "Do not include any additional information in the answer (no code block)\n"
    "Only use tables listed behind\n"
    "If you use the sql tool, write simple query. You can call the tool multiple times.\n"
)


class ReactSQLAgent(ReActAgent):
    def __init__(
        self,
        trace_manager: TraceManager,
        llm_service: LLMService,
        component_instance_name: str,
        db_service: DBService,
        tool_description: ToolDescription = DEFAULT_REACT_SQL_TOOL_DESCRIPTION,
        db_schema_name: Optional[str] = None,
        include_tables: Optional[list[str]] = None,
        additional_db_description: Optional[str] = None,
        prompt: str = DEFAULT_REACT_SQL_TOOL_PROMPT,
    ):
        kwargs = {}
        if isinstance(db_service, SnowflakeService):
            if db_schema_name is None:
                raise ValueError("db_schema_name is required for SnowflakeService")
            kwargs = {
                "schema_name": db_schema_name,
            }
            prompt += "Do not forget the add the schema name in the query.\n"
        schema = db_service.get_db_description(table_names=include_tables, **kwargs)
        initial_prompt = prompt.format(
            additional_db_description=additional_db_description, schema=schema, dialect=db_service.dialect
        )

        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
            llm_service=llm_service,
            initial_prompt=initial_prompt,
            agent_tools=[RunSQLQueryTool(trace_manager, db_service, component_instance_name="Run SQL Query Tool")],
        )

        self._db_service = db_service
