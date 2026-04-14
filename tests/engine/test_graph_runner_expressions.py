import asyncio
import json

import networkx as nx
import pytest
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.inputs_outputs.start import Start
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.field_expressions.errors import FieldExpressionError
from engine.field_expressions.serializer import from_json as expr_from_json
from engine.graph_runner.graph_runner import GraphRunner
from engine.secret import SecretValue
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_manager import TraceManager

# Deterministic migrated components for robust, predictable tests


class IntEchoInputs(BaseModel):
    input: int = Field(description="integer input")


class IntEchoOutputs(BaseModel):
    output: int


class IntEcho(Component):
    migrated = True

    @classmethod
    def get_inputs_schema(cls):
        return IntEchoInputs

    @classmethod
    def get_outputs_schema(cls):
        return IntEchoOutputs

    async def _run_without_io_trace(self, inputs: IntEchoInputs, ctx: dict) -> IntEchoOutputs:
        assert isinstance(inputs.input, int)
        return IntEchoOutputs(output=inputs.input)


class StrEcho(Component):
    """Echoes the 'input' string as output with a fixed wrapper."""

    migrated = True

    class Inputs(BaseModel):
        input: str

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return StrEcho.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return StrEcho.Outputs

    def __init__(self, trace_manager: TraceManager, name: str = "echo"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"StrEcho_{name}", description="Echo string", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return StrEcho.Outputs(output=f"echo[{inputs.input}]")


class FixedStringSource(Component):
    """Produces a fixed string regardless of inputs, for deterministic refs."""

    migrated = True

    class Inputs(BaseModel):
        input: str | None = None

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return FixedStringSource.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return FixedStringSource.Outputs

    def __init__(self, trace_manager: TraceManager, value: str, name: str):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"FixedString_{name}",
                description="Fixed string source",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )
        self._value = value

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return FixedStringSource.Outputs(output=self._value)


class FixedIntSource(Component):
    """Produces a fixed int regardless of inputs."""

    migrated = True

    class Inputs(BaseModel):
        input: int | None = None

    class Outputs(BaseModel):
        output: int

    @classmethod
    def get_inputs_schema(cls):
        return FixedIntSource.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return FixedIntSource.Outputs

    def __init__(self, trace_manager: TraceManager, value: int, name: str):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"FixedInt_{name}",
                description="Fixed int source",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )
        self._value = value

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return FixedIntSource.Outputs(output=self._value)


class DualConcat(Component):
    """Two-input component joining a and b deterministically."""

    migrated = True

    class Inputs(BaseModel):
        a: str
        b: str

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return DualConcat.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return DualConcat.Outputs

    def __init__(self, trace_manager: TraceManager, name: str = "join"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"DualConcat_{name}", description="Join a and b", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return DualConcat.Outputs(output=f"a[{inputs.a}]|b[{inputs.b}]")


class DictOutputSource(Component):
    """Source that outputs a dict with multiple keys."""

    migrated = True

    class Inputs(BaseModel):
        input: str | None = None

    class Outputs(BaseModel):
        output: dict

    @classmethod
    def get_inputs_schema(cls):
        return DictOutputSource.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return DictOutputSource.Outputs

    def __init__(self, trace_manager: TraceManager, name: str = "dict_source"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"DictSource_{name}",
                description="Dict output source",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )
        self._value = {"messages": "hello", "data": 42, "status": "ok"}

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:
        return DictOutputSource.Outputs(output=self._value)


class MessagesSink(Component):
    """Accepts list[ChatMessage] and summarizes deterministically."""

    migrated = True

    class Inputs(BaseModel):
        messages: list[ChatMessage]

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return MessagesSink.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return MessagesSink.Outputs

    def __init__(self, trace_manager: TraceManager, name: str = "sink"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"MessagesSink_{name}",
                description="Summarize messages",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        last = inputs.messages[-1].to_string() if inputs.messages else ""
        return MessagesSink.Outputs(output=f"msgs:{len(inputs.messages)} last[{last}]")


class TestGraphRunnerExpressions:
    def test_expression_derived_dependency_orders_execution(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        # A produces fixed string; B echoes with wrapper
        a = FixedStringSource(tm, value="va", name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "concat",
                    "parts": [
                        {"type": "literal", "value": "x:"},
                        {"type": "ref", "instance": "A", "port": "output"},
                    ],
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[x:va]"

    def test_non_ref_expression_overrides_mapping(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AVAL", name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "literal", "value": "OVR"}),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[OVR]"

    def test_multi_ref_concat_merges_sources(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AA", name="A")
        c = FixedStringSource(tm, value="CC", name="C")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b, "C": c}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "concat",
                    "parts": [
                        {"type": "literal", "value": "upper["},
                        {"type": "ref", "instance": "A", "port": "output"},
                        {"type": "literal", "value": "] lower["},
                        {"type": "ref", "instance": "C", "port": "output"},
                        {"type": "literal", "value": "]"},
                    ],
                }),
            }
        ]
        # Provide mapping as well; non-ref expression overrides mapping value

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A", "C"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[upper[AA] lower[CC]]"

    def test_cycle_detected_via_expression_refs(self):
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Targets must exist; migration not required for cycle detection stage
        a = StrEcho(tm, name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "ref", "instance": "A", "port": "output"}),
            },
            {
                "target_instance_id": "A",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "ref", "instance": "B", "port": "output"}),
            },
        ]

        try:
            GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm, expressions=expressions)
            assert False, "Expected cycle detection"
        except ValueError as e:
            assert "cycles" in str(e).lower()

    def test_self_loop_detected_via_expression(self):
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A"])

        a = StrEcho(tm, name="A")
        runnables = {"A": a}

        expressions = [
            {
                "target_instance_id": "A",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "ref", "instance": "A", "port": "output"}),
            }
        ]

        try:
            GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm, expressions=expressions)
            assert False, "Expected self-loop detection"
        except ValueError as e:
            assert "cycles" in str(e).lower()

    def test_invalid_field_name_validation(self):
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        a = StrEcho(tm, name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "does_not_exist",
                "expression_ast": expr_from_json({"type": "literal", "value": "x"}),
            }
        ]
        try:
            GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm, expressions=expressions)
            assert False, "Expected invalid field validation error"
        except ValueError as e:
            assert "available input fields" in str(e).lower()

    def test_invalid_target_component_validation(self):
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        a = StrEcho(tm, name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        expressions = [
            {
                "target_instance_id": "C",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "literal", "value": "x"}),
            }
        ]
        try:
            GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm, expressions=expressions)
            assert False, "Expected invalid component validation error"
        except ValueError as e:
            assert "non-existent component" in str(e).lower()

    def test_literal_expression_coerces_to_int(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        b = IntEcho(
            trace_manager=tm,
            tool_description=ToolDescription(
                name="IntEcho", description="echo int", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="B"),
        )
        runnables = {"B": b}

        g = nx.DiGraph()
        g.add_nodes_from(["B"])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "literal", "value": "42"}),
            }
        ]

        gr = GraphRunner(graph=g, runnables=runnables, start_nodes=["B"], trace_manager=tm, expressions=expressions)
        result = asyncio.run(gr.run({"input": "ignored"}))
        assert result.messages[0].content == "42"

    def test_expression_string_coerces_to_list_chatmessage(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        sink = MessagesSink(tm, name="S")
        runnables = {"S": sink}

        g = nx.DiGraph()
        g.add_nodes_from(["S"])

        expressions = [
            {
                "target_instance_id": "S",
                "field_name": "messages",
                "expression_ast": expr_from_json({"type": "literal", "value": "hello"}),
            }
        ]

        gr = GraphRunner(graph=g, runnables=runnables, start_nodes=["S"], trace_manager=tm, expressions=expressions)
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "msgs:1 last[hello]"

    def test_dual_input_with_mapping_and_expression(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AA", name="A")
        b = DualConcat(tm, name="JOIN")
        runnables = {"A": a, "JOIN": b}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "JOIN"])
        g.add_edge("A", "JOIN")

        expressions = [
            {
                "target_instance_id": "JOIN",
                "field_name": "a",
                "expression_ast": expr_from_json({"type": "ref", "instance": "A", "port": "output"}),
            },
            {
                "target_instance_id": "JOIN",
                "field_name": "b",
                "expression_ast": expr_from_json({"type": "literal", "value": "X"}),
            },
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "a[AA]|b[X]"

    def test_dual_input_expression_overrides_mapped_field(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AA", name="A")
        b = FixedStringSource(tm, value="BB", name="B")
        j = DualConcat(tm, name="JOIN")
        runnables = {"A": a, "B": b, "JOIN": j}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "JOIN"])
        g.add_edges_from([("A", "JOIN"), ("B", "JOIN")])

        expressions = [
            {
                "target_instance_id": "JOIN",
                "field_name": "a",
                "expression_ast": expr_from_json({"type": "literal", "value": "OVR"}),
            },
            {
                "target_instance_id": "JOIN",
                "field_name": "b",
                "expression_ast": expr_from_json({"type": "ref", "instance": "B", "port": "output"}),
            },
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A", "B"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "a[OVR]|b[BB]"

    def test_mixed_concat_with_int_ref(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedIntSource(tm, value=7, name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "concat",
                    "parts": [
                        {"type": "literal", "value": "num:"},
                        {"type": "ref", "instance": "A", "port": "output"},
                    ],
                }),
            }
        ]

        gr = GraphRunner(
            graph=g, runnables=runnables, start_nodes=["A", "B"], trace_manager=tm, expressions=expressions
        )
        result = asyncio.run(gr.run({"input": 42}))  # Provide integer input for FixedIntSource
        assert result.messages[0].content == "echo[num:7]"

    def test_concat_with_secret_varnode_uses_plain_value(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        b = StrEcho(tm, name="B")
        runnables = {"B": b}

        g = nx.DiGraph()
        g.add_nodes_from(["B"])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "concat",
                    "parts": [
                        {"type": "literal", "value": "Bearer "},
                        {"type": "var", "name": "api_key"},
                    ],
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["B"],
            trace_manager=tm,
            expressions=expressions,
            variables={"api_key": SecretValue("real-secret")},
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[Bearer real-secret]"


class TestGraphRunnerComplexFormulas:
    """Mixed mappings and expressions across a diamond shape."""

    def _build_diamond_graph(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AA", name="A")
        b = StrEcho(tm, name="B")
        c = StrEcho(tm, name="C")
        d = StrEcho(tm, name="D")
        runnables = {"A": a, "B": b, "C": c, "D": d}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C", "D"])
        g.add_edges_from([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "ref", "instance": "A", "port": "output"}),
            },
            {
                "target_instance_id": "C",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "ref", "instance": "A", "port": "output"}),
            },
            {
                "target_instance_id": "D",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "concat",
                    "parts": [
                        {"type": "literal", "value": "upper["},
                        {"type": "ref", "instance": "B", "port": "output"},
                        {"type": "literal", "value": "] lower["},
                        {"type": "ref", "instance": "C", "port": "output"},
                        {"type": "literal", "value": "]"},
                    ],
                }),
            },
        ]

        return tm, g, runnables, expressions

    def test_diamond_graph_execution(self):
        tm, g, runnables, expressions = self._build_diamond_graph()
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert "upper[echo[AA]]" in result.messages[0].content and "lower[echo[AA]]" in result.messages[0].content

    def test_pure_ref_with_key_extraction(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        dict_source = DictOutputSource(tm, name="A")
        str_echo = StrEcho(tm, name="B")
        runnables = {"A": dict_source, "B": str_echo}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "ref",
                    "instance": "A",
                    "port": "output",
                    "key": "messages",
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[hello]"

    def test_non_pure_ref_with_key_extraction(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        dict_source = DictOutputSource(tm, name="A")
        str_echo = StrEcho(tm, name="B")
        runnables = {"A": dict_source, "B": str_echo}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "concat",
                    "parts": [
                        {"type": "literal", "value": "prefix: "},
                        {"type": "ref", "instance": "A", "port": "output", "key": "messages"},
                    ],
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[prefix: hello]"

    def test_key_extraction_missing_key_raises(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        dict_source = DictOutputSource(tm, name="A")
        str_echo = StrEcho(tm, name="B")
        runnables = {"A": dict_source, "B": str_echo}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "ref",
                    "instance": "A",
                    "port": "output",
                    "key": "nonexistent",
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        with pytest.raises(FieldExpressionError, match="not found in dict"):
            asyncio.run(gr.run({"input": "seed"}))

    def test_key_extraction_non_dict_raises(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        str_source = FixedStringSource(tm, value="hello", name="A")
        str_echo = StrEcho(tm, name="B")
        runnables = {"A": str_source, "B": str_echo}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "ref",
                    "instance": "A",
                    "port": "output",
                    "key": "messages",
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        with pytest.raises(FieldExpressionError, match="not a dict"):
            asyncio.run(gr.run({"input": "seed"}))


class TestStartNodeIntegration:
    """Integration tests for the Start node in a real graph runner context."""

    def _make_start(self, tm: TraceManager, name: str = "start") -> Start:
        return Start(
            trace_manager=tm,
            tool_description=ToolDescription(
                name=f"Start_{name}",
                description="Start node",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )

    def test_start_extra_fields_reachable_via_field_expression(self):
        """DRA-1048 (Diana's bug): extra payload_schema fields (e.g. additional_info) used to land
        only in NodeData.ctx, invisible to @{{start.additional_info}} ref expressions that look in
        task_result.data. The downstream silently received no value and the expression was skipped.
        With the new Start, all extra fields are in NodeData.data, so the ref resolves correctly."""
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        start = self._make_start(tm)
        downstream = StrEcho(tm, name="downstream")
        runnables = {"start": start, "downstream": downstream}

        g = nx.DiGraph()
        g.add_nodes_from(["start", "downstream"])

        expressions = [
            {
                "target_instance_id": "downstream",
                "field_name": "input",
                "expression_ast": expr_from_json({
                    "type": "ref",
                    "instance": "start",
                    "port": "additional_info",
                }),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["start"],
            trace_manager=tm,
            expressions=expressions,
        )

        result = asyncio.run(gr.run({
            "messages": [{"role": "user", "content": "hi"}],
            "additional_info": "runtime_value",
            "payload_schema": json.dumps({"messages": [], "additional_info": "default_value"}),
        }))

        assert result.messages[0].content == "echo[runtime_value]"


class ListStrSink(Component):
    """Accepts list[str] input and echoes it back as JSON."""

    migrated = True

    class Inputs(BaseModel):
        items: list[str]

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return ListStrSink.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return ListStrSink.Outputs

    def __init__(self, trace_manager: TraceManager, name: str = "list_sink"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"ListStrSink_{name}",
                description="List str sink",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return ListStrSink.Outputs(output=json.dumps(inputs.items))


class ListStrSource(Component):
    """Produces a fixed list[str] output."""

    migrated = True

    class Inputs(BaseModel):
        input: str | None = None

    class Outputs(BaseModel):
        files: list[str]

    @classmethod
    def get_inputs_schema(cls):
        return ListStrSource.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return ListStrSource.Outputs

    def __init__(self, trace_manager: TraceManager, value: list[str], name: str):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"ListStrSource_{name}",
                description="List str source",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )
        self._value = value

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return ListStrSource.Outputs(files=self._value)


class TestRefExpressionPreservesListType:
    """Regression: a RefNode expression targeting a list[str] field must preserve the list
    rather than stringifying it via str(). Previously, top-level RefNodes fell through to
    evaluate_node() which called to_string(), turning ["a", "b"] into "['a', 'b']" and then
    coercion wrapped it as ["['a', 'b']"]."""

    def test_pure_ref_preserves_list_str(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        source = ListStrSource(tm, value=["file1.pdf", "file2.docx"], name="A")
        sink = ListStrSink(tm, name="B")
        runnables = {"A": source, "B": sink}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "items",
                "expression_ast": expr_from_json({"type": "ref", "instance": "A", "port": "files"}),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == '["file1.pdf", "file2.docx"]'
