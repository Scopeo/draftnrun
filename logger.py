import datetime
import inspect
import json
import logging
import logging.config
from pathlib import Path
from typing import Optional

import yaml

BASE_DIR = Path(__file__).parent.resolve()
LOGS_DIR = BASE_DIR / "logs"


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging (CloudWatch ingestion)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


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

    # JSON formatter for console output (CloudWatch ingestion)
    # File handler keeps plain text for SSH debugging
    json_formatter = JsonFormatter()
    for handler in logging.root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(json_formatter)
