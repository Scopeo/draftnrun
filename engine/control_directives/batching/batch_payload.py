from typing import Any
from pydantic import BaseModel, Field
from engine.agent.data_structures import AgentPayload


class BatchAgentPayload(BaseModel):
    """
    Explicit type for batch processing results.
    Represents a collection of AgentPayloads being processed in batch mode.
    """

    payloads: list[AgentPayload]
    batch_metadata: dict[str, Any] = Field(default_factory=dict)

    def __iter__(self):
        return iter(self.payloads)

    def __len__(self):
        return len(self.payloads)
