# Payload Schema & Data Flow

How data enters, transforms, and flows through a Draft'n Run workflow graph.

## Payload Schema (Start Node)

Every workflow begins with a Start component (`engine/components/inputs_outputs/start.py`).

The Start node's `payload_schema` input port (type JSON, `ui_component=JSON_BUILDER`, `drives_output_schema=True`) defines the workflow's input schema — a JSON object describing what fields the workflow accepts at runtime.

### Runtime Flow

1. **Merge**: `payload_schema` defaults are merged with runtime `model_extra` (extra fields passed at invocation)
2. **Extract**: `messages` is popped from the merged dict
3. **Propagate**: remaining fields are injected into `ctx` (the shared run context dictionary)
4. **Output**: `StartOutputs(messages=..., **runtime_data)` — extra fields land in both output `data` and `ctx`

### Playground Configuration

`ada_backend/services/graph/playground_utils.py`:

- `extract_payload_schema_from_instance()` reads the Start node's `payload_schema` FieldExpression literal value
- `classify_schema_fields()` categorizes each field:
  - `MESSAGES` — chat message array
  - `FILE` — file upload
  - `JSON` — complex JSON object
  - `SIMPLE` — string, number, boolean

Dynamic output ports are generated from `payload_schema` keys when `drives_output_schema=True`.

## ctx Propagation

The `run_context` dict is shared across the entire graph execution:

```text
Start node output ctx → merged into run_context
    → passed to Node A as NodeData.ctx
        → Node A output ctx merged into run_context
            → passed to Node B as NodeData.ctx
                → ...
```

Every node's output `ctx` is merged into the shared `run_context` via:

```python
self.run_context.update(result_packet.ctx or {})
```

This allows downstream nodes to access values produced by upstream nodes without explicit port wiring.

## Field Expressions

Field expressions define how data is assembled for each input port. They are JSON AST structures stored in the `field_expressions` table.

### AST Node Types

| Node Type | JSON `type` | Description | Example |
|---|---|---|---|
| `LiteralNode` | `"literal"` | Static text value | `{"type": "literal", "value": "Hello"}` |
| `RefNode` | `"ref"` | Reference to a node output | `{"type": "ref", "instance": "abc", "port": "output", "key": "name"}` |
| `VarNode` | `"var"` | Variable reference | `{"type": "var", "name": "api_key"}` |
| `ConcatNode` | `"concat"` | Concatenation of parts | `{"type": "concat", "parts": [...]}` |
| `JsonBuildNode` | `"json_build"` | Build JSON with refs | `{"type": "json_build", "template": {...}, "refs": {...}}` |

### Text Syntax

In the UI, field expressions use `@{{...}}` syntax:
- `@{{instance_id.port_name}}` → RefNode
- `@{{instance_id.port_name::key}}` → RefNode with key extraction
- `@{{var_name}}` (no dot) → VarNode
- Mixed text and refs → ConcatNode

### Evaluation Priority

In `_gather_inputs()`:

1. Direct port mappings applied first (data copied source → target, with coercion)
2. Pure `RefNode` expressions with `::key` extraction during mapping step
3. Non-ref expressions (Concat, Literal, JsonBuild, Var) evaluated and override mapped values
4. Pure refs with no mapping value (e.g. refs to `ctx` fields) evaluated as fallback

### Key Files

| File | Purpose |
|---|---|
| `engine/field_expressions/ast.py` | AST node dataclasses |
| `engine/field_expressions/parser.py` | `@{{...}}` text → AST |
| `engine/field_expressions/serializer.py` | AST → JSON dict |
| `engine/field_expressions/traversal.py` | Walk, select, map, get_pure_ref |
| `engine/graph_runner/field_expression_management.py` | Runtime evaluation against task results |

## Coercion Matrix

**File**: `engine/coercion_matrix.py`

When data flows between ports of different types, the coercion matrix defines which conversions are allowed and how they're performed. Only migrated components participate in coercion; unmigrated components receive raw data dicts.
