import datetime
import inspect
import logging
import logging.config
from pathlib import Path
from typing import Optional

import yaml

BASE_DIR = Path(__file__).parent.resolve()
LOGS_DIR = BASE_DIR / "logs"


class TracingContextFilter(logging.Filter):
    """Logging filter that adds tracing context fields to log records."""

    TRACING_FIELDS = [
        "cron_id",
        "trace_id",
    ]

    def filter(self, record):
        # Import here to avoid circular dependency
        from engine.trace.span_context import get_tracing_span

        tracing_span = get_tracing_span()

        for field_name in self.TRACING_FIELDS:
            if tracing_span and hasattr(tracing_span, field_name):
                field_value = getattr(tracing_span, field_name)
                if field_value is not None:
                    setattr(record, field_name, field_value)
            # If field doesn't exist or is None, don't set it
            # This allows the formatter to conditionally include it

        return True


class ConditionalContextFormatter(logging.Formatter):
    """Custom formatter that conditionally includes tracing context fields when present."""

    def format(self, record):
        context_parts = []

        for field_name in TracingContextFilter.TRACING_FIELDS:
            if hasattr(record, field_name) and getattr(record, field_name):
                context_parts.append(f"{field_name}=%({field_name})s")

        if context_parts:
            context_str = " - [" + ", ".join(context_parts) + "]"
            format_str = f"%(asctime)s - %(levelname)s - %(name)s{context_str} - %(message)s"
        else:
            format_str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

        formatter = logging.Formatter(format_str, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def setup_logging(
    config_path: str = "logging-config.yaml", process_name: Optional[str] = None, mode_append: bool = False
) -> None:
    if not Path(BASE_DIR / config_path).exists():
        raise FileNotFoundError(f"File {BASE_DIR / config_path} does not exist.")
    LOGS_DIR.mkdir(exist_ok=True)

    if not process_name:
        process_name = Path(inspect.stack()[1].filename).name.split(".")[0]

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    with open(BASE_DIR / config_path, "r") as file:
        config = yaml.safe_load(file)

    if "handlers" in config:
        for handler in config["handlers"].values():
            if mode_append and "filename" in handler:
                handler["filename"] = BASE_DIR / f"logs/{process_name}.log"
            elif "filename" in handler:
                handler["filename"] = BASE_DIR / f"logs/{process_name}_{timestamp}.log"
    logging.config.dictConfig(config)
