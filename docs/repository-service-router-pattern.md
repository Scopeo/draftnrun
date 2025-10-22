# Repository-Service-Router Pattern Documentation

## Overview
This document describes the proper implementation of the Repository-Service-Router pattern in the Draft'n Run codebase and documents the fix applied to ensure consistent adherence to this pattern.

## The Pattern

### Repository Layer (`ada_backend/repositories/`)
- **Purpose**: Handle database CRUD operations
- **Responsibilities**:
  - Direct database queries and mutations
  - Return data or None
  - No business logic
  - No validation beyond database constraints
- **Key Rule**: **NEVER raise business exceptions** (like `ValueError`)

### Service Layer (`ada_backend/services/`)
- **Purpose**: Business logic and orchestration
- **Responsibilities**:
  - Business validations
  - Error handling and exceptions
  - Orchestrating multiple repository calls
  - Data transformation
- **Key Rule**: **Handle None returns from repositories and raise appropriate exceptions**

### Router Layer (`ada_backend/routers/`)
- **Purpose**: HTTP request/response handling
- **Responsibilities**:
  - Route definitions
  - Request validation via Pydantic schemas
  - HTTP status codes
  - Response serialization

## The Problem Fixed

### Before (Incorrect Pattern)
```python
# In repository layer (WRONG!)
def upsert_tool_description(
    session: Session,
    name: str,
    description: str,
    tool_properties: dict,
    required_tool_properties: list[str],
    id: Optional[UUID] = None,
) -> db.ToolDescription:
    if id:
        tool_description = session.query(db.ToolDescription).filter(db.ToolDescription.id == id).first()
        if not tool_description:
            raise ValueError(f"ToolDescription with id {id} not found")  # ❌ Repository raising exception!
        # ... update logic
```

### After (Correct Pattern)
```python
# In repository layer (CORRECT)
def upsert_tool_description(
    session: Session,
    name: str,
    description: str,
    tool_properties: dict,
    required_tool_properties: list[str],
    id: Optional[UUID] = None,
) -> Optional[db.ToolDescription]:  # ✅ Returns Optional
    if id:
        tool_description = session.query(db.ToolDescription).filter(db.ToolDescription.id == id).first()
        if not tool_description:
            return None  # ✅ Repository returns None
        # ... update logic
```

```python
# In service layer (CORRECT)
def update_api_tool_service(session: Session, component_instance_id: UUID, payload: CreateSpecificApiToolRequest):
    # ... other logic

    tool_desc = upsert_tool_description(
        session=session,
        id=payload.tool_description_id,
        name=payload.tool_description_name,
        description=payload.tool_description or payload.tool_display_name,
        tool_properties=payload.tool_properties or {},
        required_tool_properties=payload.required_tool_properties or [],
    )

    # ✅ Service layer handles validation and raises exception
    if not tool_desc:
        raise ValueError(f"ToolDescription with id {payload.tool_description_id} not found")

    # ... continue processing
```

## Files Modified

1. **`ada_backend/repositories/component_repository.py`**
   - Changed `upsert_tool_description` to return `Optional[db.ToolDescription]`
   - Returns `None` instead of raising `ValueError` when ID not found

2. **`ada_backend/services/admin_tools_service.py`**
   - Added validation in `update_api_tool_service` to check for None return
   - Service layer now raises the `ValueError` with appropriate message

3. **`ada_backend/services/pipeline/update_pipeline_service.py`**
   - Added validation in `create_or_update_component_instance` to check for None return
   - Service layer now raises the `ValueError` when updating with non-existent ID

## Best Practices Going Forward

### For Repository Functions

✅ **DO:**
```python
def get_entity_by_id(session: Session, entity_id: UUID) -> Optional[db.Entity]:
    return session.query(db.Entity).filter(db.Entity.id == entity_id).first()
```

❌ **DON'T:**
```python
def get_entity_by_id(session: Session, entity_id: UUID) -> db.Entity:
    entity = session.query(db.Entity).filter(db.Entity.id == entity_id).first()
    if not entity:
        raise ValueError(f"Entity with id {entity_id} not found")  # Wrong layer!
    return entity
```

### For Service Functions

✅ **DO:**
```python
def process_entity_service(session: Session, entity_id: UUID):
    entity = get_entity_by_id(session, entity_id)
    if not entity:
        raise ValueError(f"Entity with id {entity_id} not found")
    # Process entity...
```

## Common Repository Return Patterns

1. **Single entity queries**: Return `Optional[Entity]`
2. **Multiple entity queries**: Return `list[Entity]` (empty list if none found)
3. **Count queries**: Return `int` (0 if none)
4. **Boolean checks**: Return `bool`
5. **Create/Update operations**: Return the created/updated entity (or None if update fails)

## Benefits of This Pattern

1. **Separation of Concerns**: Each layer has clear responsibilities
2. **Testability**: Repository functions can be tested without business logic
3. **Reusability**: Repository functions can be reused in different services with different validation needs
4. **Consistency**: All layers follow predictable patterns
5. **Error Handling**: Errors are handled at the appropriate layer with proper context

## Checklist for Code Reviews

When reviewing code, ensure:
- [ ] Repository functions return Optional types or None when appropriate
- [ ] Repository functions don't raise business exceptions (ValueError, etc.)
- [ ] Service functions validate repository returns and raise exceptions when needed
- [ ] Service functions provide meaningful error messages with context
- [ ] Router functions handle service exceptions and return appropriate HTTP status codes