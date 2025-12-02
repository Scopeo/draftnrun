class MissingKeyFromPromptTemplateError(Exception):
    """Raised when required keys are missing from prompt template variables."""


class WrongKeyTypeInjectionFromPromptTemplateError(Exception):
    """Raised when required keys cannot be cast as str for injection as prompt template variables."""
