import logging

from e2b_code_interpreter import AsyncSandbox

from engine.trace.span_context import get_tracing_span

LOGGER = logging.getLogger(__name__)


async def get_or_create_sandbox(api_key: str) -> tuple[AsyncSandbox, bool]:
    params = get_tracing_span()
    should_cleanup_locally = False
    sandbox: AsyncSandbox | None = None

    if params and params.shared_sandbox:
        if await params.shared_sandbox.is_running():
            LOGGER.info("Shared sandbox is running, using it")
            sandbox = params.shared_sandbox
        else:
            LOGGER.info("Shared sandbox is not running, killing it")
            await params.shared_sandbox.kill()
            params.shared_sandbox = None

    if sandbox is None:
        LOGGER.info("Creating new sandbox")
        sandbox = await AsyncSandbox.create(api_key=api_key)
        if params:
            params.shared_sandbox = sandbox
        else:
            should_cleanup_locally = True

    return sandbox, should_cleanup_locally
