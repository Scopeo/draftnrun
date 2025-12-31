import asyncio

import networkx as nx
import pytest
from pydantic import BaseModel, Field

from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.field_expressions.serializer import from_json as expr_from_json
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_manager import TraceManager
from tests.mocks.dummy_agent import DummyAgent

# Deterministic migrated components for robust, predictable tests


class IntEchoInputs(BaseModel):
    input: int = Field(description="integer input")


class IntEchoOutputs(BaseModel):
    output: int


class IntEcho(Agent):
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


class StrEcho(Agent):
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


class FixedStringSource(Agent):
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


class FixedIntSource(Agent):
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


class DualConcat(Agent):
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


class DictOutputSource(Agent):
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


class MessagesSink(Agent):
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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            expressions=expressions,
            port_mappings=mappings,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[x:va]"

    def test_pure_ref_expression_is_ignored_in_presence_of_mapping(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AVAL", name="A")
        c = FixedStringSource(tm, value="CVAL", name="C")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b, "C": c}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]
        # Pure ref expression to a different source; should be ignored at runtime, mapping wins
        expressions = [
            {
                "target_instance_id": "B",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "ref", "instance": "C", "port": "output"}),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A", "C"],
            trace_manager=tm,
            port_mappings=mappings,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "echo[AVAL]"

    def test_non_ref_expression_overrides_mapping(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])  # metrics

        a = FixedStringSource(tm, value="AVAL", name="A")
        b = StrEcho(tm, name="B")
        runnables = {"A": a, "B": b}

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]
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
            port_mappings=mappings,
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
        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A", "C"],
            trace_manager=tm,
            expressions=expressions,
            port_mappings=mappings,
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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "JOIN",
                "target_port_name": "a",
                "dispatch_strategy": "direct",
            }
        ]
        expressions = [
            {
                "target_instance_id": "JOIN",
                "field_name": "b",
                "expression_ast": expr_from_json({"type": "literal", "value": "X"}),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "JOIN",
                "target_port_name": "a",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "JOIN",
                "target_port_name": "b",
                "dispatch_strategy": "direct",
            },
        ]
        # Override 'a' via expression
        expressions = [
            {
                "target_instance_id": "JOIN",
                "field_name": "a",
                "expression_ast": expr_from_json({"type": "literal", "value": "OVR"}),
            }
        ]

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A", "B"],
            trace_manager=tm,
            port_mappings=mappings,
            expressions=expressions,
        )
        result = asyncio.run(gr.run({"input": "seed"}))
        assert result.messages[0].content == "a[OVR]|b[BB]"

    def test_expressions_for_unmigrated_target_raise(self):
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["U"])  # unmigrated target

        u = DummyAgent(tm, "U")  # unmigrated
        runnables = {"U": u}

        expressions = [
            {
                "target_instance_id": "U",
                "field_name": "input",
                "expression_ast": expr_from_json({"type": "literal", "value": "x"}),
            }
        ]

        try:
            GraphRunner(graph=g, runnables=runnables, start_nodes=["U"], trace_manager=tm, expressions=expressions)
            assert False, "Expected expressions not supported for unmigrated target"
        except ValueError as e:
            assert "expressions are not supported" in str(e).lower()

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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "D",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "C",
                "source_port_name": "output",
                "target_instance_id": "D",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        expressions = [
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
            }
        ]

        return tm, g, runnables, mappings, expressions

    def test_diamond_graph_execution(self):
        tm, g, runnables, mappings, expressions = self._build_diamond_graph()
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]
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
            port_mappings=mappings,
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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]
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
            port_mappings=mappings,
            expressions=expressions,
        )
        with pytest.raises(ValueError, match="not found in dict"):
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

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]
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
            port_mappings=mappings,
            expressions=expressions,
        )
        with pytest.raises(ValueError, match="not a dict"):
            asyncio.run(gr.run({"input": "seed"}))
