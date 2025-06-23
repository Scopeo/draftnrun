# E2B Python Sandbox Tool Implementation

## Overview

Successfully implemented a new E2B sandbox tool for executing Python code in secure, isolated cloud environments. The tool integrates seamlessly with the existing engine architecture and database structure.

## Implementation Details

### 1. Tool Engine Implementation
**File:** `engine/agent/api_tools/e2b_sandbox_tool.py`

- **Class:** `E2BSandboxTool` extending the base `Agent` class
- **Key Features:**
  - Executes Python code in isolated E2B cloud sandboxes
  - Configurable execution timeout (default: 60 seconds)
  - Configurable sandbox lifetime (default: 5 minutes)
  - Automatic cleanup and resource management
  - Error handling and detailed execution reporting
  - File listing to capture generated artifacts

- **Tool Description:**
  - Name: `e2b_python_sandbox`
  - Required properties: `python_code`
  - Optional properties: `timeout`

### 2. Database Integration

#### Component Registration
**File:** `ada_backend/database/seed/seed_e2b_tool.py`

- **Component UUID:** `e2b00000-0000-1111-2222-333333333333`
- **Component Type:** Function-callable tool (not an agent)
- **Release Stage:** Beta
- **Parameters:**
  - `e2b_api_key`: LLM_API_KEY type for secure API key storage
  - `sandbox_timeout`: Integer slider (60-1800 seconds)

#### Tool Description Registration
**File:** `ada_backend/database/seed/seed_tool_description.py`

- **Tool Description UUID:** `e2b11111-2222-3333-4444-555555555555`
- Imports and registers the E2B tool description from the engine

### 3. Dependencies and Configuration

#### Dependencies Added
**File:** `pyproject.toml`
- Added `e2b>=1.5.2,<2` to project dependencies

#### Settings Configuration
**File:** `settings.py`
- Added `E2B_API_KEY` configuration field
- Integrates with existing environment variable pattern

#### Environment Configuration
**File:** `credentials.env.example`
- Added example E2B API key configuration
- Documentation for setup requirements

### 4. Database Seeding Integration
**File:** `ada_backend/database/seed_db.py`

- Integrated E2B component seeding into main seeding pipeline
- Added import and function call to `seed_e2b_components`
- Positioned appropriately in seeding sequence

## Usage

### API Key Setup
```bash
# Get your E2B API key from https://e2b.dev/
export E2B_API_KEY=your_e2b_api_key_here
```

### Example Tool Call
```json
{
  "tool": "e2b_python_sandbox",
  "parameters": {
    "python_code": "print('Hello from E2B sandbox!')\nimport math\nprint(f'Pi is approximately {math.pi}')",
    "timeout": 30
  }
}
```

### Expected Response Format
- ✅ **Success:** Shows execution output, generated files, and success indicators
- ❌ **Error:** Shows error messages, exit codes, and failure details
- Structured artifacts with detailed execution results

## Security Features

1. **Isolated Execution:** Each code execution runs in a fresh, isolated cloud environment
2. **Timeout Protection:** Configurable timeouts prevent infinite loops and resource abuse
3. **Automatic Cleanup:** Sandboxes are automatically terminated after execution
4. **Secure API Key Management:** API keys stored using the platform's secret management system

## Architecture Benefits

1. **Consistent Pattern:** Follows the same pattern as existing tools (Tavily, API Call Tool)
2. **Database Integration:** Properly registered in component and tool description tables
3. **UI Ready:** Includes UI component definitions for frontend integration
4. **Configurable:** Supports both environment-level and instance-level configuration
5. **Observable:** Integrates with existing tracing and monitoring infrastructure

## Files Modified/Created

### New Files:
- `engine/agent/api_tools/e2b_sandbox_tool.py`
- `ada_backend/database/seed/seed_e2b_tool.py`
- `E2B_SANDBOX_TOOL_IMPLEMENTATION.md` (this file)

### Modified Files:
- `pyproject.toml` - Added E2B dependency
- `settings.py` - Added E2B_API_KEY configuration
- `ada_backend/database/seed/utils.py` - Added component UUID
- `ada_backend/database/seed/seed_tool_description.py` - Added tool description
- `ada_backend/database/seed_db.py` - Integrated seeding function
- `credentials.env.example` - Added E2B API key example

## Next Steps

1. **Install Dependencies:** Run `uv sync` to install the E2B package
2. **Database Migration:** Run database seeding to register the new component
3. **API Key Configuration:** Set up E2B API key in environment
4. **Testing:** Test the tool with various Python code examples
5. **Documentation:** Update user-facing documentation with E2B tool capabilities

## API Reference

The tool uses E2B's Python SDK with the following key features:
- **Sandbox Creation:** Creates isolated Python environments
- **Code Execution:** Runs Python code via `python3 -c` command
- **File System Access:** Can list and access generated files
- **Resource Management:** Automatic cleanup and timeout handling

For more information about E2B, visit: https://e2b.dev/docs