import json
import logging
import os
import re
import resource
import subprocess
from pathlib import Path
from typing import Any, Dict

import requests
import sentry_sdk

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate, ResultType, TaskResultMetadata
from ada_ingestion_system.worker.base_worker import BaseWorker, logger, redis_client

_LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b")
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _parse_log_level(line: str, default: int = logging.ERROR) -> int:
    """Extract the first standard log-level token from *line*."""
    m = _LEVEL_RE.search(line)
    return _LEVEL_MAP[m.group(1)] if m else default


def _is_real_error(line: str) -> bool:
    """Return True if *line* is an actual error (not just an INFO/DEBUG log on stderr)."""
    m = _LEVEL_RE.search(line)
    if m is None:
        return True  # no recognised level → treat as error (e.g. traceback, warning)
    return _LEVEL_MAP[m.group(1)] >= logging.WARNING


# Redis configuration
STREAM_NAME = os.getenv("REDIS_INGESTION_STREAM", "ada_ingestion_stream")
MAX_CONCURRENT_INGESTIONS = int(os.getenv("MAX_CONCURRENT_INGESTIONS", 2))
SUBPROCESS_MEMORY_LIMIT_MB = int(os.getenv("SUBPROCESS_MEMORY_LIMIT_MB", "4096"))


def _set_memory_limit() -> None:
    """preexec_fn callback: cap virtual address space for the child process."""
    if SUBPROCESS_MEMORY_LIMIT_MB > 0:
        limit_bytes = SUBPROCESS_MEMORY_LIMIT_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))


# Default API base URL - use HTTP for localhost
DEFAULT_API_BASE_URL = "http://localhost:8000"


class Worker(BaseWorker):
    def __init__(self):
        super().__init__(
            stream_name=STREAM_NAME,
            max_concurrent=MAX_CONCURRENT_INGESTIONS,
            worker_type="redis_ingestion",
        )

    def get_required_fields(self) -> list[str]:
        """Get required fields for ingestion task payload."""
        return ["ingestion_id"]

    def process_task(self, payload: Dict[str, Any]) -> None:
        """Process a single ingestion task."""
        try:
            ingestion_id = payload["ingestion_id"]
            sentry_sdk.set_tag("ingestion_id", ingestion_id)
            source_type = payload.get("source_type", "")
            organization_id = payload["organization_id"]
            source_name = payload.get("source_name", f"unnamed-{ingestion_id}")
            task_id = payload["task_id"]
            source_id = payload.get("source_id")

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
                "processing_task ingestion_id=%s source_type=%s organization_id=%s parameters=%s",
                ingestion_id,
                source_type,
                organization_id,
                safe_payload,
            )

            logger.info(
                "task_processing_start ingestion_id=%s source_name=%s source_type=%s"
                " organization_id=%s task_id=%s source_attribute_keys=%s",
                ingestion_id,
                source_name,
                source_type,
                organization_id,
                task_id,
                list(source_attributes.keys()) if source_attributes else [],
            )

            if source_type == db.SourceType.DATABASE.value:
                self._run_ingestion_via_api(
                    organization_id=organization_id,
                    task_id=task_id,
                    source_name=source_name,
                    source_type=source_type,
                    source_id=source_id,
                    source_attributes=source_attributes,
                    ingestion_id=ingestion_id,
                )
                return

            # Get the ada_backend path - assumes a standard structure
            ada_backend_path = Path(__file__).parents[2] / "ada_backend"
            script_path = ada_backend_path / "scripts" / "main.py"
            if not script_path.exists():
                logger.debug("script_not_found path=%s", str(script_path))
                # Try alternative path
                alt_script_path = Path(__file__).parents[2] / "ingestion_script" / "main.py"
                if alt_script_path.exists():
                    script_path = alt_script_path
                    logger.info("using_alternative_script_path path=%s", str(script_path))
                else:
                    logger.error(
                        "all_script_paths_not_found primary=%s alternative=%s",
                        str(script_path),
                        str(alt_script_path),
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

            # Use API base URL default; do not load secrets from credentials.env

            # Set API_BASE_URL to http for localhost connections
            if "API_BASE_URL" not in env:
                env["API_BASE_URL"] = DEFAULT_API_BASE_URL
                logger.info("using_default_api_base_url url=%s", DEFAULT_API_BASE_URL)
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
                (
                    f"import sys; sys.path.append('{os.path.dirname(ada_backend_path)}'); "
                    f"from {module_path} import ingestion_main; "
                    f"ingestion_main("
                    f"source_name={repr(source_name)}, "
                    f"organization_id='{organization_id}', "
                    f"task_id='{task_id}', "
                    f"source_type='{source_type}', "
                    f"source_attributes={repr(source_attributes)}, "
                    + (f"source_id='{source_id}', " if source_id else "")
                    + ")"
                ),
            ]

            # Execute the command (log without sensitive data)
            safe_cmd = cmd.copy()
            # Replace the full command with a sanitized version for logging
            if len(safe_cmd) >= 3:  # If it's the python -c command format
                # Sanitize access tokens and other sensitive data in the command
                safe_cmd[2] = safe_cmd[2].replace(repr(source_attributes), "***SANITIZED_SOURCE_ATTRIBUTES***")
                # Also sanitize any access tokens that might appear directly
                if "access_token" in safe_cmd[2]:
                    import re

                    safe_cmd[2] = re.sub(r"'access_token': '[^']*'", "'access_token': '***REDACTED***'", safe_cmd[2])
                    safe_cmd[2] = re.sub(r'"access_token": "[^"]*"', '"access_token": "***REDACTED***"', safe_cmd[2])
            logger.info("executing_command cmd=%s", " ".join(safe_cmd))
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(Path(__file__).parents[2]),
                preexec_fn=_set_memory_limit,
            )

            # Real-time logging - stream output as it happens
            import fcntl
            import select

            # Make stdout and stderr non-blocking for real-time reading
            if process.stdout:
                fd = process.stdout.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            if process.stderr:
                fd = process.stderr.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            stdout_buffer = ""
            stderr_buffer = ""
            stderr_lines = []

            # Stream output in real-time until process completes
            while process.poll() is None:
                ready, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)

                for stream in ready:
                    if stream == process.stdout:
                        try:
                            chunk = stream.read(1024).decode("utf-8", errors="replace")
                            if chunk:
                                stdout_buffer += chunk
                                # Log complete lines immediately
                                while "\n" in stdout_buffer:
                                    line, stdout_buffer = stdout_buffer.split("\n", 1)
                                    if line.strip():
                                        logger.info("script_live output=%s", line.strip())
                        except Exception:
                            pass

                    elif stream == process.stderr:
                        try:
                            chunk = stream.read(1024).decode("utf-8", errors="replace")
                            if chunk:
                                stderr_buffer += chunk
                                # Log complete lines immediately
                                while "\n" in stderr_buffer:
                                    line, stderr_buffer = stderr_buffer.split("\n", 1)
                                    if line.strip():
                                        if _is_real_error(line):
                                            stderr_lines.append(line.strip())
                                        logger.log(_parse_log_level(line), "script_live_error output=%s", line.strip())
                        except Exception:
                            pass

            # Read any remaining output after process completes
            try:
                if process.stdout:
                    remaining = process.stdout.read().decode("utf-8", errors="replace")
                    stdout_buffer += remaining
                if process.stderr:
                    remaining = process.stderr.read().decode("utf-8", errors="replace")
                    stderr_buffer += remaining
            except Exception:
                pass

            # Log any remaining buffer content
            if stdout_buffer.strip():
                for line in stdout_buffer.strip().split("\n"):
                    if line.strip():
                        logger.info("script_final output=%s", line.strip())

            if stderr_buffer.strip():
                for line in stderr_buffer.strip().split("\n"):
                    if line.strip():
                        if _is_real_error(line):
                            stderr_lines.append(line.strip())
                        logger.log(_parse_log_level(line), "script_final_error output=%s", line.strip())

            error_summary = {}
            if stderr_lines:
                stderr_text = "\n".join(stderr_lines)
                error_summary = self._parse_error_message(stderr_text)
                logger.error(
                    "script_error_summary error_type=%s error_message=%s possible_solution=%s",
                    error_summary.get("error_type"),
                    error_summary.get("error_message"),
                    error_summary.get("possible_solution"),
                )

            if process.returncode != 0:
                logger.error("script_failed return_code=%s", process.returncode)

                error_type = error_summary.get("error_type")
                error_msg = error_summary.get("error_message")
                solution = error_summary.get("possible_solution")
                if error_type and error_msg:
                    parts = [f"{error_type}: {error_msg}"]
                    if solution:
                        parts.append(f"Possible solution: {solution}")
                    message = ". ".join(parts)
                else:
                    message = f"Ingestion subprocess failed with return code {process.returncode}"

                result_metadata = TaskResultMetadata(
                    message=message,
                    type=ResultType.ERROR,
                )
                self._update_task_status_to_failed(
                    organization_id=organization_id,
                    task_id=task_id,
                    source_name=source_name,
                    source_type=source_type,
                    ingestion_id=ingestion_id,
                    result_metadata=result_metadata,
                )
            else:
                logger.info("task_completed ingestion_id=%s", ingestion_id)

        except Exception as e:
            logger.error("task_error error=%s", str(e), exc_info=True)
            # Update task status to FAILED when worker encounters an exception
            try:
                result_metadata = TaskResultMetadata(
                    message=str(e),
                    type=ResultType.ERROR,
                )
                self._update_task_status_to_failed(
                    organization_id=organization_id,
                    task_id=task_id,
                    source_name=source_name,
                    source_type=source_type,
                    ingestion_id=ingestion_id,
                    result_metadata=result_metadata,
                )
            except Exception as update_error:
                logger.error("failed_to_update_task_status error=%s", str(update_error))

    def _run_ingestion_via_api(
        self,
        organization_id: str,
        task_id: str,
        source_name: str,
        source_type: str,
        source_id: str | None,
        source_attributes: dict,
        ingestion_id: str,
    ) -> None:
        """Dispatch ingestion to the internal API endpoint."""
        api_base_url = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)
        ingestion_api_key = os.getenv("INGESTION_API_KEY")
        if not ingestion_api_key:
            logger.error("INGESTION_API_KEY not configured, cannot dispatch ingestion")
            raise ValueError("INGESTION_API_KEY not configured, cannot dispatch ingestion")
        url = f"{api_base_url}/internal/ingestion/organizations/{organization_id}/run"

        body = {
            "task_id": task_id,
            "source_name": source_name,
            "source_type": source_type,
            "ingestion_id": ingestion_id,
            "source_attributes": source_attributes or {},
        }
        if source_id:
            body["source_id"] = source_id

        logger.info("ingestion_via_api ingestion_type=%s ingestion_id=%s url=%s", source_type, ingestion_id, url)

        try:
            response = requests.post(
                url,
                json=body,
                headers={
                    "X-Ingestion-API-Key": ingestion_api_key,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code == 202:
                logger.info("ingestion_accepted ingestion_type=%s ingestion_id=%s", source_type, ingestion_id)
                return

            logger.error(
                "ingestion_api_failed ingestion_type=%s ingestion_id=%s status=%s body=%s",
                source_type,
                ingestion_id,
                response.status_code,
                response.text[:500],
            )
            self._update_task_status_to_failed(
                organization_id=organization_id,
                task_id=task_id,
                source_name=source_name,
                source_type=source_type,
                ingestion_id=ingestion_id,
                result_metadata=TaskResultMetadata(
                    message=f"Ingestion API for {source_type} returned {response.status_code}",
                    type=ResultType.ERROR,
                ),
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                "ingestion_api_error ingestion_type=%s ingestion_id=%s error=%s", source_type, ingestion_id, str(e)
            )
            self._update_task_status_to_failed(
                organization_id=organization_id,
                task_id=task_id,
                source_name=source_name,
                source_type=source_type,
                ingestion_id=ingestion_id,
                result_metadata=TaskResultMetadata(
                    message=f"Failed to reach ingestion API for {source_type}: {type(e).__name__}",
                    type=ResultType.ERROR,
                ),
            )

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

        elif "MemoryError" in stderr_text or "Cannot allocate memory" in stderr_text:
            result["error_type"] = "Out of Memory"
            result["error_message"] = "Subprocess exceeded memory limit"
            result["possible_solution"] = "Reduce source size or increase SUBPROCESS_MEMORY_LIMIT_MB"

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

    def _update_task_status_to_failed(
        self,
        organization_id: str,
        task_id: str,
        source_name: str,
        source_type: str,
        ingestion_id: str,
        result_metadata=None,
    ) -> None:
        """Update the task status to FAILED in the database."""
        try:
            failed_task = IngestionTaskUpdate(
                id=task_id,
                source_name=source_name,
                source_type=source_type,
                status=db.TaskStatus.FAILED,
                result_metadata=result_metadata,
            )

            # Get API base URL from environment or use default
            api_base_url = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)
            ingestion_api_key = os.getenv("INGESTION_API_KEY")
            if not ingestion_api_key:
                logger.error("INGESTION_API_KEY not configured, cannot update task status")
                raise ValueError("INGESTION_API_KEY not configured, cannot update task status")

            # Make the API call to update task status
            response = requests.patch(
                f"{api_base_url}/ingestion_task/{organization_id}",
                json=failed_task.model_dump(mode="json"),
                headers={
                    "x-ingestion-api-key": ingestion_api_key,
                    "Content-Type": "application/json",
                },
                timeout=10,  # Add timeout to prevent hanging
            )
            response.raise_for_status()

            logger.info(
                "task_status_updated_to_failed ingestion_id=%s task_id=%s organization_id=%s",
                ingestion_id,
                task_id,
                organization_id,
            )

        except Exception as e:
            logger.error(
                "failed_to_update_task_status_to_failed ingestion_id=%s task_id=%s organization_id=%s error=%s",
                ingestion_id,
                task_id,
                organization_id,
                str(e),
            )

    def log_redis_state(self):
        """Log current Redis state including queue contents."""
        logger.debug("redis_state_logging_start stream=%s", self.stream_name)

        try:
            ping_result = redis_client.ping()
            logger.debug("redis_ping result=%s", ping_result)

            queue_length = redis_client.xlen(self.stream_name)
            logger.debug("redis_queue_length stream=%s length=%s", self.stream_name, queue_length)

            queue_items = redis_client.xrange(self.stream_name, "-", "+", count=10)
            logger.debug("redis_queue_items_retrieved stream=%s count=%s", self.stream_name, len(queue_items))

            if queue_items:
                for message_id, fields in queue_items:
                    try:
                        raw_data = fields.get("data")
                        if raw_data is None:
                            raw_data = fields.get(b"data")
                        parsed = json.loads(raw_data)
                        logger.debug(
                            "redis_queue_item stream=%s message_id=%s keys=%s",
                            self.stream_name,
                            message_id,
                            list(parsed.keys()) if isinstance(parsed, dict) else [],
                        )
                    except json.JSONDecodeError:
                        preview = str(raw_data)[:100] if raw_data is not None else ""
                        logger.debug(
                            "redis_queue_item_invalid_json stream=%s message_id=%s preview=%s",
                            self.stream_name,
                            message_id,
                            preview,
                        )
                    except Exception as e:
                        logger.debug(
                            "redis_queue_item_error stream=%s message_id=%s error=%s",
                            self.stream_name,
                            message_id,
                            str(e),
                        )
            else:
                logger.debug("redis_queue_empty stream=%s", self.stream_name)

            try:
                all_keys = redis_client.keys("*")
                logger.debug("redis_keys count=%s keys=%s", len(all_keys), all_keys)
            except Exception as key_error:
                logger.error("redis_keys_fetch_failed error=%s", str(key_error))

        except Exception as e:
            logger.error("redis_state_logging_failed error=%s", str(e), exc_info=True)

        logger.debug("redis_state_logging_end stream=%s", self.stream_name)

    def _on_dead_letter(self, message_id: str, fields: Dict[str, str], reason: str = "") -> None:
        """Mark the ingestion task as FAILED when its message is dead-lettered."""
        try:
            raw = fields.get("data", "")
            payload = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            logger.error("dead_letter_unparseable message_id=%s", message_id)
            return

        if not isinstance(payload, dict):
            logger.error(
                "dead_letter_invalid_payload_shape message_id=%s payload_type=%s",
                message_id,
                type(payload).__name__,
            )
            return

        organization_id = payload.get("organization_id")
        task_id = payload.get("task_id")
        source_name = payload.get("source_name", "unknown")
        source_type = payload.get("source_type", "unknown")
        ingestion_id = payload.get("ingestion_id", "unknown")

        if not organization_id or not task_id:
            logger.error("dead_letter_missing_ids message_id=%s payload_keys=%s", message_id, list(payload.keys()))
            return

        logger.error(
            "dead_letter_marking_task_failed ingestion_id=%s task_id=%s organization_id=%s source_name=%s",
            ingestion_id,
            task_id,
            organization_id,
            source_name,
        )

        msg = f"Task failed after repeated crashes ({reason or 'unknown'}). Source: {source_name}, Type: {source_type}"
        result_metadata = TaskResultMetadata(
            message=msg,
            type=ResultType.ERROR,
        )
        self._update_task_status_to_failed(
            organization_id=organization_id,
            task_id=task_id,
            source_name=source_name,
            source_type=source_type,
            ingestion_id=ingestion_id,
            result_metadata=result_metadata,
        )

    def _log_queued_task(self, payload: Dict[str, Any]) -> None:
        """Log queued ingestion task."""
        logger.info("task_queued_for_external_processing ingestion_id=%s", payload.get("ingestion_id"))

    def spawn_external_worker(self, payload: Dict[str, Any]) -> None:
        """Spawn an external worker (EC2/Fargate) for the task."""
        logger.info("spawning_external_worker ingestion_id=%s", payload.get("ingestion_id"))
        # TODO: Implement AWS EC2 spawning
        pass


if __name__ == "__main__":
    worker = Worker()
    worker.run()
