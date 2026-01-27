# Field Expressions

Field expressions allow you to reference outputs from other components and build dynamic values in your graphs.

## Expression Types

### 1. LiteralNode - Static Text
Plain text values.

```python
LiteralNode(value="Hello World")
```

**JSON representation:**
```json
{"type": "literal", "value": "Hello World"}
```

---

### 2. RefNode - Component Output Reference
Reference the output of another component.

```python
RefNode(instance="abc123", port="output")
RefNode(instance="abc123", port="config", key="model")  # Extract dict key
```

**JSON representation:**
```json
{"type": "ref", "instance": "abc123", "port": "output"}
{"type": "ref", "instance": "abc123", "port": "config", "key": "model"}
```

**Text syntax:**
```
@{{abc123.output}}
@{{abc123.config::model}}
```

---

### 3. ConcatNode - String Concatenation
Concatenate multiple literals and refs into a single string.

```python
ConcatNode(parts=[
    LiteralNode(value="Hello "),
    RefNode(instance="user_comp", port="name"),
    LiteralNode(value="!")
])
```

**JSON representation:**
```json
{
  "type": "concat",
  "parts": [
    {"type": "literal", "value": "Hello "},
    {"type": "ref", "instance": "user_comp", "port": "name"},
    {"type": "literal", "value": "!"}
  ]
}
```

**Text syntax:**
```
Hello @{{user_comp.name}}!
```

**⚠️ Warning:** When refs return complex objects (lists, dicts), they are stringified! This can cause issues with JSON structures.

---

### 4. JsonBuildNode - Structured JSON Builder ✨

**NEW!** Build JSON structures (lists, dicts) with component references that **preserve their types**.

Unlike `ConcatNode` which stringifies everything, `JsonBuildNode` keeps objects as objects, lists as lists, etc.

```python
JsonBuildNode(
    template=[
        {
            "value_a": "__REF_MESSAGES__",  # Placeholder
            "operator": "is_not_empty",
            "value_b": "",
            "logical_operator": "AND"
        }
    ],
    refs={
        "__REF_MESSAGES__": RefNode(instance="abc123", port="messages")
    }
)
```

**JSON representation:**
```json
{
  "type": "json_build",
  "template": [
    {
      "value_a": "__REF_MESSAGES__",
      "operator": "is_not_empty",
      "value_b": "",
      "logical_operator": "AND"
    }
  ],
  "refs": {
    "__REF_MESSAGES__": {
      "type": "ref",
      "instance": "abc123",
      "port": "messages"
    }
  }
}
```

**How it works:**
1. Define a `template` with placeholder strings (e.g., `"__REF_MESSAGES__"`)
2. Map each placeholder to a `RefNode` in the `refs` dict
3. At evaluation time, placeholders are replaced with actual values **preserving their types**

**Example:**

If `@{{abc123.messages}}` evaluates to:
```python
[{"role": "user", "content": "Hello"}]
```

Then the JsonBuildNode result will be:
```python
[
    {
        "value_a": [{"role": "user", "content": "Hello"}],  # ← List preserved!
        "operator": "is_not_empty",
        "value_b": "",
        "logical_operator": "AND"
    }
]
```

Not a broken string like:
```python
"[{'value_a': '[{'role': 'user', 'content': 'Hello'}]', 'operator': ...}]"
```

---

## When to Use Each Type

| Use Case | Expression Type |
|----------|----------------|
| Static text | `LiteralNode` |
| Reference a component output | `RefNode` |
| Build a string with refs | `ConcatNode` |
| Build JSON/dict/list with refs | `JsonBuildNode` ✨ |

---

## Usage in Frontend

To use `JsonBuildNode` in your graph editor frontend, send field expressions with this structure:

```json
{
  "target_instance_id": "if_else_comp_123",
  "field_name": "conditions",
  "expression": {
    "type": "json_build",
    "template": [
      {
        "value_a": "__REF_0__",
        "operator": "is_not_empty",
        "value_b": "",
        "logical_operator": "AND"
      }
    ],
    "refs": {
      "__REF_0__": {
        "type": "ref",
        "instance": "upstream_comp_456",
        "port": "messages"
      }
    }
  }
}
```

---

## Migration Guide

If you have existing field expressions that concatenate JSON strings, consider migrating to `JsonBuildNode`:

### ❌ Old (Broken with nested structures):
```json
{
  "type": "concat",
  "parts": [
    {"type": "literal", "value": "[{'value_a': '"},
    {"type": "ref", "instance": "abc", "port": "messages"},
    {"type": "literal", "value": "', 'operator': 'is_not_empty'}]"}
  ]
}
```

### ✅ New (Works correctly):
```json
{
  "type": "json_build",
  "template": [{"value_a": "__MESSAGES__", "operator": "is_not_empty"}],
  "refs": {
    "__MESSAGES__": {"type": "ref", "instance": "abc", "port": "messages"}
  }
}
```
