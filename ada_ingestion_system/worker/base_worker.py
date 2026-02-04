import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

import redis
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)

dotenv_path = Path(__file__).parent.parent / ".env"
LOGGER.info(f"Loading environment variables from {dotenv_path}")
load_dotenv(dotenv_path=dotenv_path)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)


class BaseWorker:
    """Base class for Redis queue workers with common functionality."""

    def __init__(self, queue_name: str, max_concurrent: int):
        self.queue_name = queue_name
        self.max_concurrent = max_concurrent
        self.current_threads = 0
        self.lock = threading.Lock()

    def should_process_locally(self) -> bool:
        """Determine if the current worker should process the task locally."""
        with self.lock:
            if self.current_threads < self.max_concurrent:
                self.current_threads += 1
                return True
            return False

    def _decrement_thread_count(self) -> None:
        """Decrement the thread count when a task completes."""
        with self.lock:
            self.current_threads -= 1

    def process_task(self, payload: Dict[str, Any]) -> None:
        """
        Process a single task. Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement process_task")

    def _validate_payload(self, payload: Dict[str, Any], required_fields: list[str]) -> bool:
        """
        Validate that the payload contains required fields.

        Args:
            payload: The payload to validate
            required_fields: List of required field names

        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(payload, dict):
            return False
        return all(field in payload for field in required_fields)

    def run(self) -> None:
        """Main worker loop."""
        while True:
            try:
                # Block until a task is available
                _, data = redis_client.blpop(self.queue_name)

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as e:
                    LOGGER.error(f"Invalid JSON in queue {self.queue_name}: {str(e)}")
                    continue

                if not self._validate_payload(payload, self.get_required_fields()):
                    LOGGER.error(f"Invalid payload format in queue {self.queue_name}")
                    continue

                if self.should_process_locally():
                    # Process in a new thread
                    thread = threading.Thread(target=self._process_with_cleanup, args=(payload,))
                    thread.start()
                else:
                    self._log_queued_task(payload)

            except redis.ConnectionError:
                LOGGER.warning(f"Redis connection error for queue {self.queue_name}, retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                LOGGER.error(f"Unexpected error in queue {self.queue_name}: {str(e)}", exc_info=True)
                time.sleep(1)

    def _process_with_cleanup(self, payload: Dict[str, Any]) -> None:
        """Process task with automatic thread count cleanup."""
        try:
            self.process_task(payload)
        finally:
            self._decrement_thread_count()

    def get_required_fields(self) -> list[str]:
        """
        Get the list of required fields for payload validation.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement get_required_fields")

    def _log_queued_task(self, payload: Dict[str, Any]) -> None:
        """
        Log when a task is queued for external processing.
        Can be overridden by subclasses for custom logging.
        """
        LOGGER.info(f"Task queued for external processing in queue {self.queue_name}")
