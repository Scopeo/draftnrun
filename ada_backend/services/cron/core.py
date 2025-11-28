"""
Core protocols and spec for cron handlers and executors.
"""

from typing import Optional, Protocol, runtime_checkable
from pydantic import BaseModel


class BaseUserPayload(BaseModel):
    """
    Base schema for user-provided cron job payloads.
    Each cron job type should define its own UserPayload class that inherits
    from this base class and adds specific fields as needed. This is what gets
    validated by the registration validator.
    Example:
    A cron job that prints a message would define a UserPayload class like this:
    class PrintMessageUserPayload(BaseUserPayload):
        message: str

    The registration validator would then validate the user input and return an ExecutionPayload
    """


class BaseExecutionPayload(BaseModel):
    """
    Base schema for execution payloads persisted in DB and used by executors.
    Each cron job type should define its own ExecutionPayload class that inherits
    from this base class and adds specific fields as needed. This is what gets
    persisted in DB and is the single source of truth at runtime.
    Example:
    A cron job that prints a message would define an ExecutionPayload class like this:
    class PrintMessageExecutionPayload(BaseExecutionPayload):
        message: str

    - The execution validator would then validate the execution payload and return None
    - The executor would then execute the job using this payload as input and return a result dict for storage
    """


@runtime_checkable
class registration_validator(Protocol):
    def __call__(self, user_input: BaseUserPayload, **kwargs) -> BaseExecutionPayload:
        """Takes validated user input, returns the execution payload model."""
        ...


@runtime_checkable
class execution_validator(Protocol):
    def __call__(self, execution_payload: BaseExecutionPayload, **kwargs) -> None:
        """Validates runtime conditions for the execution payload."""
        ...


@runtime_checkable
class cron_job_executor(Protocol):
    async def __call__(self, execution_payload: BaseExecutionPayload, **kwargs) -> dict[str, object]:
        """Executes the job and returns a result dict for storage."""
        ...


@runtime_checkable
class post_registration_hook(Protocol):
    def __call__(self, execution_payload: BaseExecutionPayload, **kwargs) -> None:
        """
        Optional hook called after the cron job is inserted into the database.
        """
        ...


class CronEntrySpec(BaseModel):
    """
    Specification for a cron entrypoint.
    Holds models, validators and executor.
    The flow is:
    - User payload model -> Registration validator -> Execution payload model
    - Execution payload model -> Execution validator -> Executor
    """

    user_payload_model: type[BaseUserPayload]
    execution_payload_model: type[BaseExecutionPayload]
    registration_validator: registration_validator
    execution_validator: execution_validator
    executor: cron_job_executor
    post_registration_hook: Optional[post_registration_hook] = None

    class Config:
        arbitrary_types_allowed = True
