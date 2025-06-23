import logging
import json
from typing import Optional

from e2b import Sandbox
from openinference.semconv.trace import OpenInferenceSpanKindValues

from engine.agent.agent import (
    Agent,
    ChatMessage,
    AgentPayload,
    ToolDescription,
)
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

E2B_TOOL_DESCRIPTION = ToolDescription(
    name="e2b_python_sandbox",
    description="Execute Python code in a secure sandbox environment using E2B. Returns the execution result including stdout, stderr, and any generated files.",
    tool_properties={
        "python_code": {
            "type": "string",
            "description": "The Python code to execute in the sandbox.",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout for code execution in seconds. Default is 60 seconds.",
        },
    },
    required_tool_properties=["python_code"],
)


class E2BSandboxTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_instance_name: str,
        tool_description: ToolDescription = E2B_TOOL_DESCRIPTION,
        e2b_api_key: str = settings.E2B_API_KEY,
        sandbox_timeout: int = 300,  # 5 minutes default sandbox lifetime
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
        )
        self.trace_manager = trace_manager
        self.e2b_api_key = e2b_api_key
        self.sandbox_timeout = sandbox_timeout

    def execute_python_code(self, python_code: str, timeout: int = 60) -> dict:
        """Execute Python code in E2B sandbox and return the result."""
        
        if not self.e2b_api_key:
            return {
                "success": False,
                "error": "E2B API key not configured",
                "stdout": "",
                "stderr": "",
                "exit_code": 1,
            }

        try:
            # Create a new sandbox
            sandbox = Sandbox(
                api_key=self.e2b_api_key,
                timeout=self.sandbox_timeout,
            )

            try:
                # Execute the Python code
                result = sandbox.commands.run(
                    f"python3 -c {repr(python_code)}",
                    timeout=timeout,
                )
                
                # Get execution results
                execution_result = {
                    "success": result.exit_code == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                }

                # Try to list files in current directory to capture any generated files
                try:
                    files_result = sandbox.commands.run("ls -la", timeout=10)
                    if files_result.exit_code == 0:
                        execution_result["files_listing"] = files_result.stdout
                except Exception as e:
                    LOGGER.warning(f"Could not list files: {str(e)}")

                return execution_result

            finally:
                # Always clean up the sandbox
                try:
                    sandbox.kill()
                except Exception as e:
                    LOGGER.warning(f"Failed to clean up sandbox: {str(e)}")

        except Exception as e:
            LOGGER.error(f"E2B sandbox execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": 1,
            }

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        python_code: str,
        timeout: int = 60,
        **kwargs,
    ) -> AgentPayload:

        # Execute the Python code in E2B sandbox
        execution_result = self.execute_python_code(python_code, timeout)

        # Format the response
        if execution_result["success"]:
            content = f"✅ **Code executed successfully**\n\n"
            if execution_result["stdout"]:
                content += f"**Output:**\n```\n{execution_result['stdout']}\n```\n\n"
            if execution_result.get("files_listing"):
                content += f"**Generated files:**\n```\n{execution_result['files_listing']}\n```"
            if not execution_result["stdout"] and not execution_result.get("files_listing"):
                content += "No output generated."
        else:
            content = f"❌ **Code execution failed**\n\n"
            if execution_result["stderr"]:
                content += f"**Error:**\n```\n{execution_result['stderr']}\n```\n\n"
            if execution_result.get("error"):
                content += f"**System Error:** {execution_result['error']}\n\n"
            content += f"**Exit Code:** {execution_result['exit_code']}"

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            artifacts={"execution_result": execution_result},
            is_final=False,
        )