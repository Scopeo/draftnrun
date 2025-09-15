class CronServiceError(Exception):
    """Base exception for cron service errors."""


class CronValidationError(CronServiceError):
    """Raised when user payload or parameters are invalid."""


class CronJobNotFound(CronServiceError):
    """Raised when a cron job cannot be found."""


class CronJobAccessDenied(CronServiceError):
    """Raised when accessing a cron job from a different organization."""


class CronSchedulerError(CronServiceError):
    """Raised when scheduling or updating the scheduler fails."""
