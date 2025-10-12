# Unified Parameter System - Phase 3 Plan

## Overview

Phase 3 is the **legacy system removal phase**. After Phase 1 (backend GraphRunner support) and Phase 2 (API layer integration) are complete and stable, Phase 3 will remove the old `port_mappings` and `parameter_templates` systems entirely.

## Current State (After Phase 2)

### What Works Now
- ✅ **Unified parameter system** (`node_parameters`) fully functional
- ✅ **All value types supported**: static, reference, and hybrid
- ✅ **Priority system**: `node_parameters` > `port_mappings` > `parameter_templates`
- ✅ **Full backward compatibility**: existing workflows continue to work
- ✅ **Validation**: Invalid component references caught at initialization

### Dual System Architecture
Currently, the system maintains **both** old and new approaches:

**GraphRunner** (`engine/graph_runner/graph_runner.py`):
- Accepts 3 parameter sources: `node_parameters`, `port_mappings`, `parameter_templates`
- `_gather_inputs()` checks all three sources with priority order
- Legacy code paths still active for backward compatibility

**API Layer** (`ada_backend/services/agent_runner_service.py`):
- Extracts parameters into **both** `node_parameters` and `parameter_templates`
- Passes both to GraphRunner constructor
- Maintains duplicate data structures

## Phase 3 Objectives

**Goal**: Simplify the codebase by removing legacy systems after confirming all workflows are migrated.

### 1. Pre-Phase 3 Validation Period

Before starting Phase 3, ensure:
- [ ] All production workflows tested with unified parameter system
- [ ] No errors in logs related to parameter resolution
- [ ] All edge cases validated (static, reference, hybrid values)
- [ ] Frontend fully supports unified parameter editing (no legacy references)

**Recommended Duration**: 2-4 weeks of production usage

### 2. Database Migration

Even though the unified system doesn't require schema changes, we need to verify data consistency:

#### Steps:
1. **Audit legacy data structures**:
   ```sql
   -- Count workflows still using port_mappings table
   SELECT COUNT(*) FROM port_mappings;

   -- Check for parameter templates in component_instance.basic_parameters
   SELECT COUNT(*)
   FROM basic_parameter
   WHERE value LIKE '%{{@%}}%';
   ```

2. **Verify all parameters in unified format**:
   - All component parameters stored in `basic_parameters` table
   - No orphaned port_mappings
   - No stale template references

3. **Backup before changes**:
   ```bash
   # Full database backup
   pg_dump ada_database > backup_before_phase3.sql
   ```

### 3. Code Removal Plan

#### 3.1 Backend Changes

**File**: `engine/graph_runner/graph_runner.py`

**Remove**:
- [ ] `port_mappings` parameter from `__init__`
- [ ] `parameter_templates` parameter from `__init__`
- [ ] `self.port_mappings` attribute
- [ ] `self.parameter_templates` attribute
- [ ] `_validate_parameter_templates()` method (no longer needed)
- [ ] Legacy branches in `_gather_inputs()` that process port_mappings
- [ ] Legacy branches in `_gather_inputs()` that process parameter_templates

**Simplify**:
```python
def _gather_inputs(self, node_id: str) -> dict[str, Any]:
    """Assembles the input data for a node using unified parameters."""
    input_data: dict[str, Any] = {}

    # Process unified parameters
    unified_params = self.node_parameters.get(node_id, {})
    if unified_params:
        resolved_outputs = self._get_resolved_outputs()

        for param_name, param_value in unified_params.items():
            if isinstance(param_value, str) and ParameterInterpolator.is_template(param_value):
                resolved_value = ParameterInterpolator.resolve_template(param_value, resolved_outputs)
                input_data[param_name] = resolved_value
            else:
                input_data[param_name] = param_value

    return input_data
```

#### 3.2 API Layer Changes

**File**: `ada_backend/services/agent_runner_service.py`

**Remove**:
- [ ] `parameter_templates` dictionary extraction
- [ ] `node_templates` dictionary in loop
- [ ] Logic that populates `parameter_templates`
- [ ] `parameter_templates=parameter_templates` from GraphRunner call

**Simplify**:
```python
async def build_graph_runner(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
) -> GraphRunner:
    # ... existing setup code ...

    node_parameters: dict[str, dict[str, Any]] = {}

    for component_node in component_nodes:
        # ... instantiate component ...

        # Extract parameters (unified system only)
        unified_params: dict[str, Any] = {}
        component_instance = get_component_instance_by_id(session, component_node.id)

        if component_instance and component_instance.basic_parameters:
            for param in component_instance.basic_parameters:
                if param.value is not None and param.value != "":
                    param_name = param.parameter_definition.name
                    unified_params[param_name] = param.value

        if unified_params:
            node_parameters[str(component_node.id)] = unified_params

    # ... build graph ...

    return GraphRunner(
        graph,
        runnables,
        start_nodes,
        trace_manager=trace_manager,
        node_parameters=node_parameters,
    )
```

#### 3.3 Database Schema Changes (Optional)

These are **optional** cleanup steps - the system works without them:

**Consider deprecating** (not removing yet, for rollback safety):
- [ ] `port_mappings` table → Mark as deprecated in comments
- [ ] Port mapping repository methods → Mark as deprecated

**Do NOT remove**:
- `basic_parameters` table (this is the storage for unified parameters)
- `parameter_definitions` table (defines available parameters)

### 4. Test Updates

#### 4.1 Remove Legacy Tests
- [ ] Tests that specifically test `port_mappings` alone
- [ ] Tests that specifically test `parameter_templates` alone

#### 4.2 Keep Essential Tests
- ✅ `test_unified_parameters.py` (7 tests) - KEEP
- ✅ `test_parameter_template_validation.py` (4 tests) - KEEP
- ✅ Any tests that verify backward compatibility - REMOVE after Phase 3

#### 4.3 Update Remaining Tests
- [ ] Update any tests that instantiate GraphRunner to only use `node_parameters`
- [ ] Remove `port_mappings` and `parameter_templates` from test fixtures

### 5. Documentation Updates

#### 5.1 Update Developer Documentation
- [ ] Remove references to `port_mappings` in architecture docs
- [ ] Remove references to `parameter_templates` in API docs
- [ ] Update GraphRunner docstrings to only mention `node_parameters`

#### 5.2 Update Migration Guides
- [ ] Create "Phase 3 Complete" announcement for developers
- [ ] Document the simplified parameter system
- [ ] Update code examples in documentation

### 6. Rollback Plan

In case issues are discovered after Phase 3 deployment:

#### Quick Rollback (< 1 hour)
1. Revert Git commit that removed legacy systems
2. Redeploy previous version
3. No data loss (database unchanged)

#### Data Rollback (if database was modified)
1. Restore from `backup_before_phase3.sql`
2. Revert code changes
3. Investigate issues before retry

### 7. Phase 3 Checklist

Execute in this order:

- [ ] **Week 1-2**: Monitor production for any parameter-related issues
- [ ] **Week 3**: Run database audit queries, verify data consistency
- [ ] **Week 4**: Create full database backup
- [ ] **Week 4**: Update tests (remove legacy, keep unified)
- [ ] **Week 4**: Remove legacy code from GraphRunner
- [ ] **Week 4**: Remove legacy code from API layer
- [ ] **Week 4**: Update documentation
- [ ] **Week 5**: Deploy to staging environment
- [ ] **Week 5**: Run full integration test suite
- [ ] **Week 5**: Deploy to production
- [ ] **Week 6+**: Monitor for issues, iterate if needed

## Success Criteria

Phase 3 is complete when:

✅ No `port_mappings` or `parameter_templates` parameters in GraphRunner
✅ No legacy extraction logic in `build_graph_runner()`
✅ All tests passing with only `node_parameters`
✅ Production workflows running smoothly
✅ Codebase simplified (fewer lines, clearer logic)
✅ Documentation updated

## Estimated Effort

- **Code Removal**: 2-4 hours
- **Test Updates**: 2-3 hours
- **Documentation**: 1-2 hours
- **Testing & Validation**: 1 week
- **Total**: ~2 weeks including validation period

## Risk Assessment

**Low Risk** because:
- Database schema unchanged (can rollback instantly)
- Unified system already proven in production
- Legacy code only removed, not modified
- Full backup taken before changes

**Mitigation**:
- Staged rollout (staging → production)
- Monitoring dashboard for parameter errors
- Quick rollback procedure documented
