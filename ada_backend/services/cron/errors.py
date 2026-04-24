from uuid import UUID

from ada_backend.services.errors import ServiceError


class CronServiceError(ServiceError):
    """Base exception for cron service errors."""


class CronValidationError(CronServiceError):
    """Raised when user payload or parameters are invalid."""
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)


class CronJobNotFound(CronServiceError):
    """Raised when a cron job cannot be found."""
    status_code = 404

    def __init__(self, cron_job_id: UUID):
        self.cron_job_id: UUID = cron_job_id
        super().__init__(f"Cron job {cron_job_id} not found")


class CronJobAccessDenied(CronServiceError):
    """Raised when accessing a cron job from a different organization."""
    status_code = 403

    def __init__(self, cron_job_id: UUID, organization_id: UUID):
        self.cron_job_id: UUID = cron_job_id
        self.organization_id: UUID = organization_id
        super().__init__(f"Cron job {cron_job_id} does not belong to organization {organization_id}")
