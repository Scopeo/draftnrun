# Graph Execution Engine

The engine executes workflow graphs (DAGs) of components. Each component is a typed processing unit with Pydantic I/O schemas, connected via port mappings and field expressions.

## GraphRunner

**File**: `engine/graph_runner/graph_runner.py`

The `GraphRunner` takes a `networkx.DiGraph`, a dict of `Runnable` instances keyed by instance ID, and optional port mappings, expressions, and variables.

### Initialization

1. Converts raw mappings into `PortMapping` dataclasses, builds `_mappings_by_target` index
2. Adds a virtual `__input__` node with edges to all start nodes
3. Auto-generates default mappings for single-predecessor nodes (`_synthesize_default_mappings`)
4. Augments graph edges from port mapping and expression dependencies (`_augment_graph_with_dependencies`)
5. Validates the graph is acyclic and all mappings/expressions are valid

### Execution Loop (`_run_without_io_trace`)

1. **Initialize**: Create `Task` objects for every node with `pending_deps = in_degree(node)`. Complete the virtual `__input__` with initial data.
2. **Main loop**: Find next `READY` task (pending_deps == 0)
3. For each ready node:
   - `_gather_inputs()` — assemble input dict from port mappings + field expressions
   - Wrap into `NodeData(data=..., ctx=run_context)`
   - Call `runnable.run(input_packet)`
   - Normalize output to `NodeData`
   - Merge output `ctx` back into shared `run_context`
4. **Handle directive** from result:
   - `CONTINUE` — decrement all successors' pending deps
   - `HALT` — BFS-mark downstream (and branch roots skipped by selective routing) as `HALTED` with empty `NodeData` (nodes already `COMPLETED`, e.g. the halting node, are left unchanged)
   - `SELECTIVE_EDGE_INDICES` — only specific successors proceed based on edge `order` attribute
5. **Collect outputs**: Gather leaf node results into final response

### Task States

```text
NOT_READY → READY (pending_deps reaches 0) → COMPLETED (after execution)
NOT_READY → HALTED (branch skipped; empty NodeData; excluded from legacy leaf output collection)
```

## Component Protocol

**Files**: `engine/graph_runner/runnable.py`, `engine/components/component.py`

### Runnable Protocol

```python
class Runnable(Protocol):
    tool_description: ToolDescription
    async def run(self, *inputs) -> AgentPayload | NodeData
    def get_canonical_ports(cls) -> Dict[str, Optional[str]]
    def get_inputs_schema(cls) -> Type[BaseModel]
    def get_outputs_schema(cls) -> Type[BaseModel]
```

### Component ABC

The concrete base class implementing `Runnable`. Key attributes:
- `migrated: bool = False` — distinguishes new (typed I/O) vs legacy components

**`run()` dispatches based on migration status:**
- **Migrated**: validates inputs against `get_inputs_schema()`, calls `_run_without_io_trace(inputs, ctx)`, validates output, extracts `ExecutionDirective`
- **Unmigrated**: converts `NodeData` to legacy `AgentPayload`, calls `_run_without_io_trace()`, converts back

**`_run_without_io_trace(inputs: BaseModel, ctx: dict) -> BaseModel`** is the abstract method subclasses implement.

## Port System

Four layers spanning database (backend) and runtime (engine):

### Layer 1: PortDefinition (catalogue)

**Table**: `port_definitions` — static I/O schema per component version.

Key fields: `name`, `port_type` (INPUT/OUTPUT), `is_canonical`, `parameter_type`, `ui_component`, `drives_output_schema`.

### Layer 2: PortInstance (per graph instance)

Uses joined-table polymorphism:
- **`InputPortInstance`**: adds `field_expression_id` FK — links a configured value (FieldExpression) to an input port
- **`OutputPortInstance`**: materializes dynamic output ports (e.g. from `drives_output_schema`)

### Layer 3: PortMapping (wiring between instances)

**Table**: `port_mappings` — connects a source output to a target input within a graph.

Two mutually exclusive source FKs: `source_port_definition_id` (catalogue) or `source_output_port_instance_id` (dynamic).

Engine flattens to: `PortMapping(source_instance_id, source_port_name, target_instance_id, target_port_name, dispatch_strategy)`

### Layer 4: FieldExpression (transforms)

**Table**: `field_expressions` — JSONB AST stored in `expression_json`.

See [payload-and-data-flow.md](payload-and-data-flow.md) for the AST format.

## ExecutionDirective

**File**: `engine/components/types.py`

Controls post-node execution flow:

| Strategy | Behavior |
|---|---|
| `CONTINUE` | Default — all successors execute |
| `HALT` | Successors of the halting node (already `COMPLETED`) are marked `HALTED` with empty data |
| `SELECTIVE_EDGE_INDICES` | Only edges matching listed `order` indices proceed; non-selected successors and their subgraphs marked `HALTED` |

Used by: Router (selective routing), IfElse (halt branch).

## Variable Resolution

**File**: `ada_backend/services/variable_resolution_service.py`

Merge order: **defaults → set_ids[0] → set_ids[1] → ...**

1. Load all `VariableDefinition` rows for the org
2. Apply defaults (secret type → secret row with `set_id=None`; other → `definition.default_value`)
3. Layer variable sets in order, each overriding previous values
4. Returns `dict[str, Any]` consumed by `VarNode` expression evaluation

## Legacy Compatibility

**File**: `engine/legacy_compatibility.py` (marked for deletion after migration)

Bridges unmigrated components (using `AgentPayload` in/out) with the new multi-port `NodeData` system. Key indicators:
- `Component.migrated = False` — checked in `run()`, `_gather_inputs()`, `validate_port_mappings()`
- Unmigrated components don't use coercion and receive the entire `task_result.data` dict
- Port mapping validation is lenient when unmigrated components are involved

## Key Files

| Concept | File |
|---|---|
| GraphRunner | `engine/graph_runner/graph_runner.py` |
| Runnable Protocol | `engine/graph_runner/runnable.py` |
| Component ABC | `engine/components/component.py` |
| Task / PortMapping (engine) | `engine/graph_runner/types.py` |
| NodeData / ExecutionDirective | `engine/components/types.py` |
| Port management | `engine/graph_runner/port_management.py` |
| Field expression AST | `engine/field_expressions/ast.py` |
| Expression evaluation | `engine/graph_runner/field_expression_management.py` |
| Coercion matrix | `engine/coercion_matrix.py` |
| Legacy compatibility | `engine/legacy_compatibility.py` |
| Variable resolution | `ada_backend/services/variable_resolution_service.py` |
| DB models (ports) | `ada_backend/database/models.py` — search for `PortMapping`, `PortDefinition` |
