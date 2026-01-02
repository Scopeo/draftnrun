from typing import Optional

from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.storage_service.db_service import DBService
from engine.trace.trace_manager import TraceManager

DEFAULT_RUN_SQL_QUERY_TOOL_DESCRIPTION = ToolDescription(
    name="Run_SQL_Query_Tool",
    description=("Execute an SQL query and return the result."),
    tool_properties={
        "sql_query": {
            "type": "string",
            "description": "The SQL query to be executed.",
        },
    },
    required_tool_properties=["sql_query"],
)


class RunSQLQueryTool(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        db_service: DBService,
        component_attributes: ComponentAttributes,
        tool_description: Optional[ToolDescription] = DEFAULT_RUN_SQL_QUERY_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._db_service = db_service

    async def _run_without_io_trace(
        self, *inputs: AgentPayload, sql_query: str, ctx: Optional[dict] = None
    ) -> AgentPayload:
        sql_output = self._db_service.run_query(sql_query).to_markdown(index=False)
        return AgentPayload(messages=[ChatMessage(role="assistant", content=sql_output)])
