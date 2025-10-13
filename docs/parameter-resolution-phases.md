# Parameter Resolution Phases

## Overview
Parameters in Draft'n Run can now be resolved at two different times:

1. **Constructor Phase** - When the component is instantiated
2. **Runtime Phase** - When the component is executed

This is controlled by the `resolution_phase` field on each `BasicParameter`.

## Constructor Parameters

Resolved once when the component is created. Used for:
- API keys and authentication
- Model configuration (e.g., `model_name`, `temperature`)
- Static configuration values
- Component behavior settings

### Example
```python
# In the database
parameter = BasicParameter(
    component_instance_id=instance_id,
    parameter_definition_id=param_def_id,
    value="gpt-4",
    resolution_phase=ParameterResolutionPhase.CONSTRUCTOR
)
```

These parameters are:
- Passed to the component's `__init__()` method
- Resolved once at instantiation time
- Cannot reference dynamic values from other nodes

## Runtime Parameters

Resolved every time the component runs. Used for:
- Dynamic inputs from other components
- Template strings with references like `{{@node.port}}`
- User-provided data
- Values that change between executions

### Example
```python
# In the database
parameter = BasicParameter(
    component_instance_id=instance_id,
    parameter_definition_id=param_def_id,
    value="{{@input_block.instructions}}",
    resolution_phase=ParameterResolutionPhase.RUNTIME
)
```

These parameters are:
- Passed to the component's `.run()` method
- Resolved during each graph execution
- Can reference outputs from other nodes using template syntax

## How It Works

### Backend Processing

1. **Component Instantiation** (`agent_builder_service.py`):
   - `get_component_params()` filters parameters by `resolution_phase`
   - Only `CONSTRUCTOR` parameters are passed to `__init__()`
   - `RUNTIME` parameters are skipped during instantiation

2. **Graph Execution** (`graph_runner.py`):
   - `RUNTIME` parameters are resolved during `_gather_inputs()`
   - Template references are interpolated with actual values
   - Resolved values are passed to component's `.run()` method

### Database Schema

The `basic_parameters` table now includes:
```sql
resolution_phase ENUM('constructor', 'runtime') NOT NULL DEFAULT 'constructor'
```

### Migration Logic

Existing parameters are automatically classified:
- If parameter name matches an INPUT port name → `RUNTIME`
- Otherwise → `CONSTRUCTOR`

This maintains backward compatibility with existing workflows.

## API Usage

### Creating a Parameter

```python
from ada_backend.repositories.component_repository import upsert_basic_parameter
from ada_backend.database.models import ParameterResolutionPhase

# Constructor parameter
upsert_basic_parameter(
    session=session,
    component_instance_id=instance_id,
    parameter_definition_id=param_def_id,
    value="api-key-123",
    resolution_phase=ParameterResolutionPhase.CONSTRUCTOR
)

# Runtime parameter
upsert_basic_parameter(
    session=session,
    component_instance_id=instance_id,
    parameter_definition_id=param_def_id,
    value="{{@previous_node.output}}",
    resolution_phase=ParameterResolutionPhase.RUNTIME
)
```

### Frontend TypeScript

```typescript
// Types available in node.types.ts
export enum ParameterResolutionPhase {
  CONSTRUCTOR = 'constructor',
  RUNTIME = 'runtime'
}

export interface Parameter {
  // ... other fields ...
  resolution_phase?: ParameterResolutionPhase
}
```

## Best Practices

### Choosing the Right Phase

| Use Case | Resolution Phase | Reason |
|----------|-----------------|---------|
| API Keys | `CONSTRUCTOR` | Security credentials shouldn't change during execution |
| Model Name | `CONSTRUCTOR` | Component behavior should be consistent |
| Temperature | `CONSTRUCTOR` | Configuration value |
| System Prompt | `RUNTIME` | May contain template references |
| User Message | `RUNTIME` | Changes with each execution |
| Input Data | `RUNTIME` | Comes from other nodes |

### Template References

Only `RUNTIME` parameters support template references:
- ✅ `{{@input_block.message}}` - Works in RUNTIME
- ❌ `{{@input_block.api_key}}` - Won't work in CONSTRUCTOR

## Benefits

1. **Performance**: Constructor parameters resolved once, not repeatedly
2. **Clarity**: Explicit about when parameters are used
3. **Flexibility**: Different resolution strategies for different needs
4. **Type Safety**: Frontend knows parameter timing requirements

## Migration Guide

### For Existing Systems

No action required! The migration automatically:
1. Adds `resolution_phase` column with default `CONSTRUCTOR`
2. Updates existing parameters based on port name matching
3. Maintains backward compatibility

### For New Development

Always specify `resolution_phase` when creating parameters:
```python
# Be explicit about resolution timing
resolution_phase=ParameterResolutionPhase.CONSTRUCTOR  # or .RUNTIME
```

## Troubleshooting

### Parameter Not Available in Component

**Symptom**: Parameter value is `None` in component's `__init__()`

**Cause**: Parameter marked as `RUNTIME` instead of `CONSTRUCTOR`

**Solution**: Update `resolution_phase` to `CONSTRUCTOR`:
```sql
UPDATE basic_parameters
SET resolution_phase = 'constructor'
WHERE id = '<parameter_id>';
```

### Template Not Resolving

**Symptom**: Template string `{{@node.port}}` passed literally

**Cause**: Parameter marked as `CONSTRUCTOR` instead of `RUNTIME`

**Solution**: Update `resolution_phase` to `RUNTIME`:
```sql
UPDATE basic_parameters
SET resolution_phase = 'runtime'
WHERE id = '<parameter_id>';
```

## Future Enhancements

Potential future improvements:
- **Conditional Resolution**: Parameters resolved based on conditions
- **Lazy Resolution**: Parameters resolved only when accessed
- **Caching**: Cache resolved values for performance
- **Validation**: Type checking at resolution time