class EngineError(Exception):
    """Base for all custom engine errors.

    Subclasses represent expected, domain-meaningful failure modes:
    configuration problems, external-service failures, invalid expressions, etc.
    """
