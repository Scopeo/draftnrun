from ada_backend.services.errors import ServiceError


class CronServiceError(ServiceError):
    """Base exception for cron service errors."""


class CronValidationError(CronServiceError):
    """Raised when user payload or parameters are invalid."""
    status_code = 400


class CronJobNotFound(CronServiceError):
    """Raised when a cron job cannot be found."""
    status_code = 404


class CronJobAccessDenied(CronServiceError):
    """Raised when accessing a cron job from a different organization."""
    status_code = 403
