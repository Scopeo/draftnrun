import logging
from typing import Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import load_str_to_json
from engine.components.utils_prompt import fill_prompt_template
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_TABLE_LOOKUP_TOOL_DESCRIPTION = ToolDescription(
    name="Table_Lookup_Tool",
    description="A table lookup tool that performs key-value lookup based on a mapping dictionary.",
    tool_properties={
        "lookup_key": {
            "type": "string",
            "description": "The key to look up in the table mapping.",
        },
    },
    required_tool_properties=["lookup_key"],
)


class TableLookupInputs(BaseModel):
    lookup_key: str = Field(description="The key to look up in the table mapping.")


class TableLookupOutputs(BaseModel):
    lookup_value: str = Field(description="The value returned from the table mapping.")


class TableLookup(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "lookup_key", "output": "lookup_value"}

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return TableLookupInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return TableLookupOutputs

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        table_mapping: str,
        default_value: str = "",
        tool_description: ToolDescription = DEFAULT_TABLE_LOOKUP_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        try:
            self._table_mapping = load_str_to_json(table_mapping)
        except ValueError as e:
            raise ValueError(f"Invalid 'table_mapping' parameter: {e}") from e

        if not isinstance(self._table_mapping, dict):
            raise ValueError("'table_mapping' must be a JSON object/dictionary")

        self._default_value = default_value

    async def _run_without_io_trace(
        self,
        inputs: TableLookupInputs,
        ctx: dict,
    ) -> TableLookupOutputs:
        lookup_key = inputs.lookup_key
        input_dict = inputs.model_dump(exclude_none=True)

        merged_dict = {**(ctx or {}), **input_dict}

        lookup_key = fill_prompt_template(
            prompt_template=lookup_key,
            component_name=self.component_attributes.component_instance_name,
            variables=merged_dict,
        )

        if lookup_key in self._table_mapping:
            lookup_value = str(self._table_mapping[lookup_key])
        else:
            lookup_value = self._default_value

        return TableLookupOutputs(lookup_value=lookup_value)
