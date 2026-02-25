class MissingKeyPromptTemplateError(Exception):
    """Raised when required keys are missing from prompt template variables."""

    def __init__(self, missing_keys: list[str]):
        self.missing_keys = missing_keys
        message = f"Missing template variable(s) {missing_keys} needed in prompt template."
        super().__init__(message)


class KeyTypePromptTemplateError(Exception):
    """Raised when required keys cannot be cast as str for injection as prompt template variables."""

    def __init__(self, key: str, error: Exception):
        self.key = key
        self.error = error
        message = f"Value for key '{key}' cannot be cast to string: {error}"
        super().__init__(message)


class MCPConnectionError(Exception):
    """Raised when an MCP tool cannot connect to its endpoint (HTTP/SSE or stdio)."""

    def __init__(self, endpoint: str, detail: str):
        super().__init__(f"MCP Tool failed to connect to {endpoint}: {detail}")


class NoMatchingRouteError(Exception):
    """Raised when no route condition matches in a Router component."""

    def __init__(self, num_routes: int, routes_info: str = ""):
        self.num_routes = num_routes
        message = (
            f"No matching route found. "
            f"Evaluated {num_routes} route(s) but none matched. "
            f"Check your route conditions and input values."
        )
        if routes_info:
            message += f"\n{routes_info}"
        super().__init__(message)
