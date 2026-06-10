import logging

from e2b_code_interpreter import AsyncSandbox

from engine.trace.span_context import get_tracing_span

LOGGER = logging.getLogger(__name__)


async def _clear_shared_sandbox(params, reason: str) -> None:
    sandbox = params.shared_sandbox
    if sandbox is None:
        return
    params.shared_sandbox = None
    LOGGER.warning("Discarding shared E2B sandbox: %s", reason)
    try:
        await sandbox.kill()
    except RuntimeError as e:
        LOGGER.warning("Failed to kill discarded shared E2B sandbox: %s", e)
    except Exception as e:
        LOGGER.warning("Failed to kill discarded shared E2B sandbox: %s", e, exc_info=True)


async def get_or_create_sandbox(api_key: str) -> tuple[AsyncSandbox, bool]:
    params = get_tracing_span()
    should_cleanup_locally = False
    sandbox: AsyncSandbox | None = None

    if params and params.shared_sandbox:
        try:
            is_running = await params.shared_sandbox.is_running()
        except RuntimeError as e:
            await _clear_shared_sandbox(params, str(e))
            is_running = False
        except Exception as e:
            await _clear_shared_sandbox(params, str(e))
            is_running = False

        if is_running:
            LOGGER.info("Shared sandbox is running, using it")
            sandbox = params.shared_sandbox
        else:
            LOGGER.info("Shared sandbox is not running, killing it")
            if params.shared_sandbox:
                await _clear_shared_sandbox(params, "shared sandbox is not running")

    if sandbox is None:
        LOGGER.info("Creating new sandbox")
        sandbox = await AsyncSandbox.create(api_key=api_key)
        if params:
            params.shared_sandbox = sandbox
        else:
            should_cleanup_locally = True

    return sandbox, should_cleanup_locally
