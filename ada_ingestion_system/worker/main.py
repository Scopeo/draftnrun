import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict

import redis
import structlog
from dotenv import load_dotenv

# Configure structured logging
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Define the path to the .env file relative to this script
dotenv_path = Path(__file__).parent.parent / ".env"

# Load environment variables from the specific .env file
logger.info(f"Loading environment variables from {dotenv_path}")
load_dotenv(dotenv_path=dotenv_path)

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
QUEUE_NAME = "ada_ingestion_queue"
MAX_CONCURRENT_INGESTIONS = int(os.getenv("MAX_CONCURRENT_INGESTIONS", 2))

# Initialize Redis connection
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

# Default API base URL - use HTTP for localhost
DEFAULT_API_BASE_URL = "http://localhost:8000"


class Worker:
    def __init__(self):
        self.max_concurrent = MAX_CONCURRENT_INGESTIONS
        self.current_threads = 0
        self.lock = threading.Lock()

    def process_ingestion(self, payload: Dict[str, Any]) -> None:
        """Process a single ingestion task."""
        try:
            ingestion_id = payload["ingestion_id"]
            source_type = payload.get("source_type", "")
            organization_id = payload["organization_id"]
            source_name = payload.get("source_name", f"unnamed-{ingestion_id}")
            task_id = payload["task_id"]

            # Get source attributes from nested structure if present
            source_attributes = payload.get("source_attributes", {})

            # Log all parameters received (except sensitive ones)
            safe_payload = {k: v for k, v in payload.items() if k != "access_token" and k != "source_attributes"}
            if "source_attributes" in payload:
                safe_attrs = payload["source_attributes"].copy() if payload["source_attributes"] else {}
                if "access_token" in safe_attrs:
                    safe_attrs["access_token"] = "***REDACTED***" if safe_attrs["access_token"] else "MISSING"
                if "source_db_url" in safe_attrs:
                    safe_attrs["source_db_url"] = "***REDACTED***" if safe_attrs["source_db_url"] else "MISSING"
                safe_payload["source_attributes"] = safe_attrs

            logger.info(
                "processing_task",
                ingestion_id=ingestion_id,
                source_type=source_type,
                organization_id=organization_id,
                parameters=safe_payload,
            )

            # Get the ada_backend path - assumes a standard structure
            ada_backend_path = Path(__file__).parents[2] / "ada_backend"
            script_path = ada_backend_path / "scripts" / "main.py"
            if not script_path.exists():
                logger.error("script_not_found", path=str(script_path))
                # Try alternative path
                alt_script_path = Path(__file__).parents[2] / "ingestion_script" / "main.py"
                if alt_script_path.exists():
                    script_path = alt_script_path
                    logger.info("using_alternative_script_path", path=str(script_path))
                else:
                    logger.error(
                        "all_script_paths_not_found", primary=str(script_path), alternative=str(alt_script_path)
                    )
                    return

            # Prepare the Python command to run the script
            python_cmd = "python"  # Use the system Python runner
            # TODO: Find alternative (start)
            # Create a custom environment with required variables
            env = os.environ.copy()

            # Add critical environment variables if they don't exist
            # Generate a Fernet key if it doesn't exist (for testing only)
            if "FERNET_KEY" not in env:
                import base64
                import secrets

                # Generate a secure Fernet key (32 url-safe base64-encoded bytes)
                fernet_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                env["FERNET_KEY"] = fernet_key
                logger.info("generated_fernet_key_for_subprocess")

            # Set Google API key from credentials.env if not present
            if source_type == "GOOGLE_DRIVE" and "GOOGLE_API_KEY" not in env:
                # Try to read from credentials.env if available
                creds_path = Path(__file__).parents[2] / "credentials.env"
                if creds_path.exists():
                    try:
                        with open(creds_path, "r") as f:
                            for line in f:
                                if line.strip() and not line.strip().startswith("#"):
                                    if "=" in line:
                                        key, value = line.strip().split("=", 1)
                                        if key.strip() == "GOOGLE_API_KEY":
                                            env["GOOGLE_API_KEY"] = value.strip()
                                            logger.info("loaded_google_api_key_from_credentials")
                                            break
                    except Exception as e:
                        logger.error("error_reading_credentials: {}".format(str(e)))

            # Set API_BASE_URL to http for localhost connections
            if "API_BASE_URL" not in env:
                env["API_BASE_URL"] = DEFAULT_API_BASE_URL
                logger.info("using_default_api_base_url", url=DEFAULT_API_BASE_URL)
            # TODO: Find alternative (end)

            # Determine the script module path based on the script location
            if "ada_backend/scripts" in str(script_path):
                module_path = "ada_backend.scripts.main"
            else:
                module_path = "ingestion_script.main"

                # Create command to run the script as a separate process
            cmd = [
                python_cmd,
                "-c",
                f"import sys; sys.path.append('{os.path.dirname(ada_backend_path)}'); "
                f"from {module_path} import ingestion_main; "
                f"ingestion_main("
                f"source_name={repr(source_name)}, "
                f"organization_id='{organization_id}', "
                f"task_id='{task_id}', "
                f"source_type='{source_type}', "
                f"source_attributes={repr(source_attributes)}"
                f")",
            ]

            # Execute the command
            logger.info("executing_command", cmd=" ".join(cmd))
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,  # Use our custom environment with the Fernet key
                cwd=str(Path(__file__).parents[2]),  # Run from repository root
            )

            # Stream and log output
            stdout, stderr = process.communicate()

            if stdout:
                logger.info("script_stdout", output=stdout.decode())
            if stderr:
                stderr_text = stderr.decode()
                # Parse and format error for better readability
                error_summary = self._parse_error_message(stderr_text)
                logger.error("script_error_summary", **error_summary)
                logger.error("script_stderr", output=stderr_text)

            if process.returncode != 0:
                logger.error("script_failed", return_code=process.returncode)
            else:
                logger.info("task_completed", ingestion_id=ingestion_id)

        except Exception as e:
            logger.error("task_error", error=str(e), exc_info=True)
        finally:
            with self.lock:
                self.current_threads -= 1

    def _parse_error_message(self, stderr_text: str) -> dict:
        """Parse error messages to provide a cleaner summary."""
        result = {
            "error_type": "Unknown Error",
            "error_message": "An unknown error occurred",
            "possible_solution": None,
        }

        # Look for common errors
        if "FERNET_KEY is not set" in stderr_text:
            result["error_type"] = "Environment Error"
            result["error_message"] = "FERNET_KEY is not set in the environment"
            result["possible_solution"] = "Set FERNET_KEY environment variable"

        elif "Missing key inputs argument!" in stderr_text:
            result["error_type"] = "Google AI API Error"
            result["error_message"] = "Missing Google AI API credentials"
            result["possible_solution"] = "Set GOOGLE_API_KEY environment variable"

        elif "pyarrow" in stderr_text and "incompatible version" in stderr_text:
            # This is just a warning, not an error
            pass

        elif "SSL" in stderr_text and "WRONG_VERSION_NUMBER" in stderr_text:
            result["error_type"] = "SSL Connection Error"
            result["error_message"] = "SSL connection failed to localhost"
            result["possible_solution"] = "Set API_BASE_URL environment variable to http://localhost:8000"

        # Add new error pattern for module not found
        elif "ModuleNotFoundError" in stderr_text:
            module_match = "No module named" in stderr_text
            if module_match:
                result["error_type"] = "Module Not Found Error"
                result["error_message"] = "Required module not found"
                result["possible_solution"] = "Install missing dependencies with 'poetry add [package]'"

        else:
            # Extract the actual error message from Python traceback
            traceback_lines = stderr_text.strip().split("\n")
            error_lines = [line for line in traceback_lines if "Error:" in line or "ValueError:" in line]

            if error_lines:
                error_line = error_lines[-1]  # Get the last error message
                result["error_type"] = error_line.split(":", 1)[0].strip()
                if len(error_line.split(":", 1)) > 1:
                    result["error_message"] = error_line.split(":", 1)[1].strip()

        return result

    def log_redis_state(self):
        """Log current Redis state including queue contents."""
        logger.info("Begin Redis state logging")

        try:
            # Test Redis connection
            ping_result = redis_client.ping()
            logger.info("Redis connectivity test: {}".format(ping_result))

            # Get queue length
            queue_length = redis_client.llen(QUEUE_NAME)
            logger.info("Current queue length: {}".format(queue_length))

            # Get queue contents (up to 10 items)
            queue_items = redis_client.lrange(QUEUE_NAME, 0, 9)
            logger.info("Queue items retrieved: {}".format(len(queue_items)))

            if queue_items:
                logger.info("Queue preview (up to 10 items):")
                for i, item in enumerate(queue_items):
                    try:
                        parsed = json.loads(item)
                        logger.info("  Item {}: {}".format(i, json.dumps(parsed)))
                    except json.JSONDecodeError:
                        logger.info("  Item {} (not valid JSON): {}...".format(i, item[:100]))
                    except Exception as e:
                        logger.info("  Error processing item {}: {}".format(i, str(e)))
            else:
                logger.info("Queue is empty")

            # Get other Redis keys
            try:
                all_keys = redis_client.keys("*")
                logger.info("All Redis keys: {}".format(all_keys))
            except Exception as key_error:
                logger.error("Failed to get Redis keys: {}".format(str(key_error)))

        except redis.ConnectionError as ce:
            logger.error("Redis connection error during state logging: {}".format(str(ce)))
        except redis.AuthenticationError as ae:
            logger.error("Redis authentication error during state logging: {}".format(str(ae)))
        except Exception as e:
            logger.error("Error logging Redis state: {}".format(str(e)), exc_info=True)

        logger.info("End Redis state logging")

    def should_process_locally(self) -> bool:
        """Determine if the current worker should process the task locally."""
        with self.lock:
            if self.current_threads < self.max_concurrent:
                self.current_threads += 1
                return True
            return False

    def spawn_external_worker(self, payload: Dict[str, Any]) -> None:
        """Spawn an external worker (EC2/Fargate) for the task."""
        logger.info("Spawning external worker")
        # TODO: Implement AWS EC2 spawning
        pass

    def run(self) -> None:
        """Main worker loop."""
        while True:
            try:
                # Block until a task is available
                _, data = redis_client.blpop(QUEUE_NAME)

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error("invalid_json", error=str(e))
                    continue

                if not isinstance(payload, dict) or "ingestion_id" not in payload:
                    logger.error("invalid_task_format", data=data)
                    continue

                if self.should_process_locally():
                    # Process in a new thread
                    thread = threading.Thread(target=self.process_ingestion, args=(payload,))
                    thread.start()
                else:
                    logger.info("task_queued_for_external_processing", ingestion_id=payload["ingestion_id"])

            except redis.ConnectionError:
                time.sleep(5)
            except Exception as e:
                logger.error("unexpected_error", error=str(e))
                time.sleep(1)


if __name__ == "__main__":

    worker = Worker()
    worker.run()
