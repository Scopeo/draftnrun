import datetime
import inspect
import logging.config
from pathlib import Path
from typing import Optional

import yaml

BASE_DIR = Path(__file__).parent.resolve()
LOGS_DIR = BASE_DIR / "logs"


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
