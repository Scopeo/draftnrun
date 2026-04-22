from engine.errors import EngineError


class FieldExpressionError(EngineError):
    pass


class FieldExpressionParseError(FieldExpressionError):
    def __init__(self, message: str):
        super().__init__(message)
