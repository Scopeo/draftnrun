from engine.agent.agent import AgentPayload
from .batch_payload import BatchAgentPayload


class BatchEnd:
    """
    Control directive that merges multiple AgentPayloads into a single AgentPayload.
    Marks the end of batch processing mode in the workflow.
    """

    def __init__(self, separator: str = "\n"):
        """Example parameter - actual implementation details to be added later."""
        self.separator = separator

    async def __call__(self, batch_agent_payload: BatchAgentPayload) -> AgentPayload:
        """
        Merge BatchAgentPayload into single AgentPayload.

        Args:
            batch_agent_payload: BatchAgentPayload containing multiple AgentPayloads to merge.

        Returns:
            Single AgentPayload with merged content
        """
        # TODO: Implement merging logic
        pass
