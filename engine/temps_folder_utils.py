from pathlib import Path

from engine.trace.span_context import get_tracing_span


def get_output_dir() -> Path:
    params = get_tracing_span()
    if not params.uuid_for_temp_folder:
        raise ValueError("UUID for temp folder is not set")

    output_dir = Path(params.uuid_for_temp_folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
