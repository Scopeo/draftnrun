from typing import List
from engine.agent.data_structures import AgentPayload
from .batch_payload import BatchAgentPayload


class BatchStart:
    """
    Control directive that splits a single AgentPayload into multiple AgentPayloads.
    Marks the beginning of batch processing mode in the workflow.
    """

    def __init__(self, n_chunks: int = 5):
        """Example parameter - actual implementation details to be added later."""
        self.n_chunks = n_chunks

    async def __call__(self, inputs: List[AgentPayload]) -> BatchAgentPayload:
        """
        Split single AgentPayload into BatchAgentPayload.

        Args:
            inputs: List containing single AgentPayload to split

        Returns:
            BatchAgentPayload containing the split chunks
        """
        # TODO: Implement splitting logic
        pass
