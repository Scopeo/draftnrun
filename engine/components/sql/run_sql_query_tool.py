from typing import Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from ada_backend.database.models import UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
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


class RunSQLQueryToolInputs(BaseModel):
    sql_query: str = Field(
        description="The SQL query to be executed.",
        json_schema_extra={
            "is_tool_input": True,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="SQL Query",
                placeholder="SELECT * FROM table_name LIMIT 10",
                description="The SQL query to execute against the database.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class RunSQLQueryToolOutputs(BaseModel):
    output: str = Field(description="The raw SQL query result in markdown format.")


class RunSQLQueryTool(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return RunSQLQueryToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return RunSQLQueryToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "sql_query", "output": "output"}

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
        self,
        inputs: RunSQLQueryToolInputs,
        ctx: Optional[dict] = None,
    ) -> RunSQLQueryToolOutputs:
        sql_output = self._db_service.run_query(inputs.sql_query).to_markdown(index=False)
        return RunSQLQueryToolOutputs(output=sql_output)
