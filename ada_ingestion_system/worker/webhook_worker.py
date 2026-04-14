import fcntl
import json
import os
import select
import subprocess
from pathlib import Path
from typing import Any, Dict

import httpx

from ada_ingestion_system.worker.base_worker import BaseWorker, ProcessTaskOutcome, logger

# Redis configuration
WEBHOOK_STREAM_NAME = os.getenv("REDIS_WEBHOOK_STREAM", "ada_webhook_stream")
MAX_CONCURRENT_WEBHOOKS = int(os.getenv("MAX_CONCURRENT_WEBHOOKS", 2))


class WebhookExecutionError(RuntimeError):
    """Raised when webhook script execution fails."""


def _classify_script_failure(stderr_output: str) -> ProcessTaskOutcome:
    if "WEBHOOK_FAILURE_CLASS=fatal" in stderr_output:
        return ProcessTaskOutcome.FAIL_FATAL_ACK
    return ProcessTaskOutcome.FAIL_RETRY


class WebhookWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            stream_name=WEBHOOK_STREAM_NAME,
            max_concurrent=MAX_CONCURRENT_WEBHOOKS,
            worker_type="redis_webhook",
        )

    def get_required_fields(self) -> list[str]:
        """Get required fields for webhook payload."""
        return ["webhook_id", "provider", "event_id", "organization_id", "payload"]

    def process_task(self, payload: Dict[str, Any]) -> ProcessTaskOutcome:
        """Process a single webhook event by executing the webhook script."""
        try:
            webhook_id = payload["webhook_id"]
            provider = payload["provider"]
            event_id = payload["event_id"]
            organization_id = payload["organization_id"]
            webhook_payload = payload["payload"]
            run_id = payload.get("run_id")

            logger.info(
                "processing_webhook webhook_id=%s provider=%s event_id=%s organization_id=%s run_id=%s",
                webhook_id,
                provider,
                event_id,
                organization_id,
                run_id,
            )

            # Get the ada_backend path - assumes a standard structure
            ada_backend_path = Path(__file__).parents[2]
            script_path = ada_backend_path / "webhook_scripts" / "webhook_main.py"
            if not script_path.exists():
                logger.error("script_not_found path=%s", str(script_path))
                return ProcessTaskOutcome.FAIL_FATAL_ACK

            # Prepare the Python command to run the script
            python_cmd = "python"  # Use the system Python runner
            # Create a custom environment with required variables
            env = os.environ.copy()

            # Create command to run the script as a separate process
            module_path = "webhook_scripts.webhook_main"
            run_id_arg = f"run_id={repr(run_id)}, " if run_id else ""
            cmd = [
                python_cmd,
                "-c",
                (
                    f"import sys; sys.path.append('{os.path.dirname(ada_backend_path)}'); "
                    f"from {module_path} import webhook_main; "
                    f"webhook_main("
                    f"webhook_id='{webhook_id}', "
                    f"provider={repr(provider)}, "
                    f"event_id={repr(event_id)}, "
                    f"organization_id={repr(organization_id)}, "
                    f"{run_id_arg}"
                    f"payload={repr(webhook_payload)}"
                    f")"
                ),
            ]

            # Execute the command (log without sensitive data)
            safe_cmd = cmd.copy()
            if len(safe_cmd) >= 3:
                # Sanitize payload in the command for logging
                safe_cmd[2] = safe_cmd[2].replace(repr(webhook_payload), "***SANITIZED_PAYLOAD***")
            logger.info("executing_command cmd=%s", " ".join(safe_cmd))

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(Path(__file__).parents[2]),  # Run from repository root
            )

            # Real-time logging - stream output as it happens
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
            raw_stderr = ""

            # Stream output in real-time until process completes
            while process.poll() is None:
                ready, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)

                for stream in ready:
                    if stream == process.stdout:
                        try:
                            chunk = stream.read(1024).decode("utf-8", errors="replace")
                            if chunk:
                                stdout_buffer += chunk
                                while "\n" in stdout_buffer:
                                    line, stdout_buffer = stdout_buffer.split("\n", 1)
                                    if line.strip():
                                        logger.info("script_stdout output=%s", line.strip())
                        except Exception:
                            pass

                    elif stream == process.stderr:
                        try:
                            chunk = stream.read(1024).decode("utf-8", errors="replace")
                            if chunk:
                                raw_stderr += chunk
                                stderr_buffer += chunk
                                while "\n" in stderr_buffer:
                                    line, stderr_buffer = stderr_buffer.split("\n", 1)
                                    if line.strip():
                                        logger.info("script_stderr output=%s", line.strip())
                        except Exception:
                            pass

            # Read any remaining output after process completes
            try:
                if process.stdout:
                    remaining = process.stdout.read().decode("utf-8", errors="replace")
                    stdout_buffer += remaining
                if process.stderr:
                    remaining = process.stderr.read().decode("utf-8", errors="replace")
                    raw_stderr += remaining
                    stderr_buffer += remaining
            except Exception:
                pass

            # Log any remaining buffer content
            if stdout_buffer.strip():
                for line in stdout_buffer.strip().split("\n"):
                    if line.strip():
                        logger.info("script_stdout output=%s", line.strip())

            if stderr_buffer.strip():
                for line in stderr_buffer.strip().split("\n"):
                    if line.strip():
                        logger.info("script_stderr output=%s", line.strip())

            if process.returncode != 0:
                failure_output = "\n".join([stdout_buffer, raw_stderr])
                outcome = _classify_script_failure(failure_output)
                logger.error(
                    "script_failed return_code=%s stderr=%s stdout=%s outcome=%s",
                    process.returncode,
                    stderr_buffer.strip(),
                    stdout_buffer.strip(),
                    outcome.value,
                )
                return outcome
            else:
                logger.info(
                    "webhook_processing_completed webhook_id=%s event_id=%s",
                    webhook_id,
                    event_id,
                )
                return ProcessTaskOutcome.SUCCESS_ACK

        except (KeyError, TypeError, ValueError) as e:
            logger.error("webhook_processing_fatal_payload_error error=%s", str(e), exc_info=True)
            return ProcessTaskOutcome.FAIL_FATAL_ACK
        except (WebhookExecutionError, httpx.HTTPError) as e:
            logger.error("webhook_processing_error error=%s", str(e), exc_info=True)
            return ProcessTaskOutcome.FAIL_RETRY
        except Exception as e:
            logger.error("webhook_processing_error error=%s", str(e), exc_info=True)
            return ProcessTaskOutcome.FAIL_RETRY

    def _fail_run(self, fields: Dict[str, str], error_message: str, error_type: str) -> None:
        """Mark the pre-created run as FAILED via the internal API."""
        try:
            raw = fields.get("data", "")
            payload = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            logger.error("fail_run_unparseable_payload")
            return

        run_id = payload.get("run_id")
        project_id = payload.get("webhook_id")
        if not run_id or not project_id:
            return

        api_base_url = os.getenv("ADA_URL", "http://localhost:8000")
        webhook_api_key = os.getenv("WEBHOOK_API_KEY", "")

        logger.error(
            "failing_run run_id=%s project_id=%s event_id=%s error_type=%s",
            run_id,
            project_id,
            payload.get("event_id"),
            error_type,
        )

        try:
            response = httpx.patch(
                f"{api_base_url}/internal/webhooks/projects/{project_id}/runs/{run_id}/fail",
                json={"error": {"message": error_message, "type": error_type}},
                headers={"X-Webhook-API-Key": webhook_api_key, "Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("fail_run_request_failed run_id=%s error=%s", run_id, str(e))

    def _on_dead_letter(self, message_id: str, fields: Dict[str, str], reason: str = "") -> None:
        self._fail_run(
            fields,
            error_message=f"Webhook processing failed after repeated crashes: {reason}",
            error_type="DeadLetter",
        )

    def _on_fatal_ack(self, message_id: str, fields: Dict[str, str], reason: str = "") -> None:
        self._fail_run(
            fields,
            error_message=f"Webhook processing failed with non-retryable error: {reason}",
            error_type="FatalError",
        )

    def _log_queued_task(self, payload: Dict[str, Any]) -> None:
        """Log queued webhook task."""
        logger.info(
            "webhook_queued_for_processing webhook_id=%s event_id=%s",
            payload.get("webhook_id"),
            payload.get("event_id"),
        )


if __name__ == "__main__":
    worker = WebhookWorker()
    worker.run()
