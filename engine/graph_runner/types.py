"""
Graph Runner Types

This module contains the core data structures used by the GraphRunner system.
"""

from enum import StrEnum
from dataclasses import dataclass
from typing import Optional

from engine.agent.types import NodeData


class TaskState(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"
    COMPLETED = "completed"


@dataclass
class Task:
    """Tracks task data and state."""

    pending_deps: int
    state: TaskState = TaskState.NOT_READY
    result: Optional[NodeData] = None

    def decrement_pending_deps(self):
        """Decrement pending dependencies, marking the task as ready
        if dependencies are now satisfied."""
        if self.state != TaskState.NOT_READY:
            raise ValueError("Cannot decrement pending dependencies for a non-ready task")

        if self.pending_deps <= 0:
            raise ValueError("Pending dependencies cannot be negative")
        self.pending_deps -= 1

        if self.pending_deps == 0:
            self.state = TaskState.READY

    def complete(self, result: NodeData):
        """Mark the task as completed with a result."""
        if self.state != TaskState.READY:
            raise ValueError("Cannot complete a non-ready task")
        self.state = TaskState.COMPLETED
        self.result = result


@dataclass
class PortMapping:
    """A structured representation of a connection between two nodes' ports."""

    source_instance_id: str
    source_port_name: str
    target_instance_id: str
    target_port_name: str
    dispatch_strategy: str = "direct"
