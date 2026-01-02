from datetime import datetime
from typing import Optional
from uuid import UUID

import strawberry
from strawberry import field

from ada_backend.database.models import EnvType


@strawberry.type
class GraphRunnerEnvType:
    id: UUID
    env: Optional[EnvType]


@strawberry.type
class ProjectType:
    id: UUID
    name: str
    description: Optional[str]
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
    graph_runners: list[GraphRunnerEnvType] = field(default_factory=list)
