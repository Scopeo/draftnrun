# E2B Python Code Interpreter Test

This directory contains a comprehensive test suite for the E2B Python code interpreter tool that runs against the real E2B service.

## Prerequisites

1. **E2B API Key**: You need a valid E2B API key to run these tests. Get one from [E2B's website](https://e2b.dev/).

2. **Environment Setup**: Set your E2B API key as an environment variable:
   ```bash
   export E2B_API_KEY=your_api_key_here
   ```

3. **Dependencies**: The `e2b-code-interpreter` package is already included in the project dependencies.

## Running the Tests

### Option 1: Using the provided script (Recommended)
```bash
cd tests/agent
python run_e2b_test.py
```

### Option 2: Using pytest directly
```bash
# From the project root
pytest tests/agent/test_python_code_interpreter_e2b_tool.py -v

# Or from the tests/agent directory
pytest test_python_code_interpreter_e2b_tool.py -v
```

### Option 3: Run specific test functions
```bash
# Run only simple code execution test
pytest tests/agent/test_python_code_interpreter_e2b_tool.py::test_execute_simple_python_code -v

# Run only async tests
pytest tests/agent/test_python_code_interpreter_e2b_tool.py -m "anyio" -v
```

## Test Coverage

The test suite covers the following scenarios:

### Basic Functionality
- ✅ Tool initialization and configuration
- ✅ Tool description structure validation
- ✅ Simple Python code execution
- ✅ Code with standard library imports
- ✅ Error handling (division by zero, etc.)

### Advanced Features
- ✅ File operations (read/write files)
- ✅ Data processing and calculations
- ✅ Complex data structures (dictionaries, lists)
- ✅ Async execution via `_run_without_trace`

### Edge Cases
- ✅ Missing API key handling
- ✅ Sandbox timeout configuration
- ✅ Error propagation

## Test Structure

Each test function follows this pattern:
1. **Setup**: Define Python code to execute
2. **Execution**: Call the E2B tool with the code
3. **Validation**: Check stdout, stderr, and result values
4. **Cleanup**: Automatic cleanup handled by E2B

## Example Test Output

```
✅ E2B_API_KEY is set
🧪 Running E2B test: /path/to/test_python_code_interpreter_e2b_tool.py
==================================================
test_tool_initialization PASSED
test_tool_description_structure PASSED
test_execute_simple_python_code PASSED
test_execute_python_code_with_imports PASSED
test_execute_python_code_with_error PASSED
test_execute_python_code_with_file_operations PASSED
test_execute_python_code_with_data_processing PASSED
test_run_without_trace_simple_code PASSED
test_run_without_trace_complex_code PASSED
test_missing_api_key PASSED
test_sandbox_timeout_configuration PASSED
==================================================
✅ All tests passed!
```

## Troubleshooting

### Common Issues

1. **"E2B API key not configured"**
   - Make sure you've set the `E2B_API_KEY` environment variable
   - Check that the API key is valid and active

2. **"Tests skipped"**
   - The tests will be skipped if `E2B_API_KEY` is not set
   - This is intentional to avoid running tests without proper configuration

3. **Network timeouts**
   - E2B sandbox creation can take a few seconds
   - Tests have a 30-second timeout by default
   - Increase `sandbox_timeout` if needed

4. **Import errors**
   - Make sure all dependencies are installed: `uv sync`
   - The `e2b-code-interpreter` package should be available

### Debug Mode

To run tests with more verbose output:
```bash
pytest tests/agent/test_python_code_interpreter_e2b_tool.py -v -s --tb=long
```

## Integration with CI/CD

For CI/CD pipelines, make sure to:
1. Set the `E2B_API_KEY` as a secret environment variable
2. Consider running these tests in a separate job to avoid blocking other tests
3. Handle test failures gracefully (E2B service might be temporarily unavailable)

## Notes

- These tests make real API calls to E2B's service
- Each test creates a new sandbox environment
- Sandboxes are automatically cleaned up after each test
- Tests are designed to be idempotent and safe to run multiple times 