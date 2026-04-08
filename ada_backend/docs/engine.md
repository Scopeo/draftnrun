# Graph Execution Engine

The engine executes workflow graphs (DAGs) of components. Each component is a typed processing unit with Pydantic I/O schemas, connected via field expressions.

## GraphRunner

**File**: `engine/graph_runner/graph_runner.py`

The `GraphRunner` takes a `networkx.DiGraph`, a dict of `Runnable` instances keyed by instance ID, and optional expressions and variables.

### Initialization

1. Adds a virtual `__input__` node with edges to all start nodes
2. Builds `_expressions_by_node` index: per-target-node list of `(field_name, expression_ast)` from raw expression dicts
3. Augments graph edges from expression ref dependencies (`_augment_graph_with_dependencies`)
4. Validates the graph is acyclic and all expressions are valid

### Execution Loop (`_run_without_io_trace`)

1. **Initialize**: Create `Task` objects for every node with `pending_deps = in_degree(node)`. Complete the virtual `__input__` with initial data.
2. **Main loop**: Find next `READY` task (pending_deps == 0)
3. For each ready node:
   - `_gather_inputs()` — assemble input dict from field expressions; start nodes with no real predecessors are seeded with the initial input data
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

### Component Catalog Lifecycle

When removing a component from the product, delete the runtime class, registry entry, seed data, existing DB catalog rows (with a migration), default tool description, and wrapper components that only exist to call it. Leaving only part of the catalog wiring in place can keep a dead component instantiable through backend seeds or MCP graph validation even after it disappears from the front-end.

## Port System

Three layers spanning database (backend) and runtime (engine):

### Layer 1: PortDefinition (catalogue)

**Table**: `port_definitions` — static I/O schema per component version.

Key fields: `name`, `port_type` (INPUT/OUTPUT), `is_canonical`, `parameter_type`, `ui_component`, `drives_output_schema`.

### Layer 2: PortInstance (per graph instance)

Uses joined-table polymorphism:
- **`InputPortInstance`**: adds `field_expression_id` FK — links a configured value (FieldExpression) to an input port
- **`OutputPortInstance`**: materializes dynamic output ports (e.g. from `drives_output_schema`)

### Layer 3: FieldExpression (wiring and transforms)

**Table**: `field_expressions` — JSONB AST stored in `expression_json`. This is the sole wiring mechanism between components; there is no separate port_mappings table.

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
- `Component.migrated = False` — checked in `run()` and `_gather_inputs()`
- Unmigrated components don't use coercion and receive the entire `task_result.data` dict

## SQL Local Storage Lifecycle

`SQLLocalService` caches SQLAlchemy engines by `engine_url` at process level instead of creating one pool per
instantiation. This prevents connection-pool growth when services are repeatedly created for the same database URL
(notably ingestion DB flows).
In ingestion flows, prefer reusing an existing `SQLLocalService` instance inside the same job and always call
`await close()` in `finally` blocks to release ref-counted engine ownership.
In ingestion workers, `ingestion_script.ingest_db_source.upload_db_source()` should create one source
`SQLLocalService` per ingestion run and reuse it across the run before closing it in `finally`.

## Key Files

| Concept | File |
|---|---|
| GraphRunner | `engine/graph_runner/graph_runner.py` |
| Runnable Protocol | `engine/graph_runner/runnable.py` |
| Component ABC | `engine/components/component.py` |
| Task (engine) | `engine/graph_runner/types.py` |
| NodeData / ExecutionDirective | `engine/components/types.py` |
| Port management | `engine/graph_runner/port_management.py` |
| Field expression AST | `engine/field_expressions/ast.py` |
| Expression evaluation | `engine/graph_runner/field_expression_management.py` |
| Coercion matrix | `engine/coercion_matrix.py` |
| Legacy compatibility | `engine/legacy_compatibility.py` |
| Variable resolution | `ada_backend/services/variable_resolution_service.py` |
| DB models (ports) | `ada_backend/database/models.py` — search for `PortDefinition`, `PortInstance` |
| OTel span → SQL (`traces` DB) | `engine/trace/sql_exporter.py` — `SQLSpanExporter` parses each span once and passes the JSON dict into export |
