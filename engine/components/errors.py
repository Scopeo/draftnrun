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


class RemoteMCPConnectionError(Exception):
    """Raised when RemoteMCPTool cannot reach the MCP server."""

    def __init__(self, server_url: str, detail: str):
        super().__init__(f"MCP Tool failed to connect to {server_url}: {detail}")
