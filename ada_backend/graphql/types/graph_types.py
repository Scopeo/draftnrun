import json
from typing import Any
from uuid import UUID

import strawberry


@strawberry.type
class UpdateComponentInstancePayload:
    component_instance_id: UUID
    component_instance: strawberry.scalars.JSON


@strawberry.type
class DeleteComponentInstancePayload:
    deleted_instance_id: UUID
    deleted_edge_ids: list[UUID]


@strawberry.type
class AddEdgePayload:
    edge_id: UUID


@strawberry.type
class DeleteEdgePayload:
    deleted_edge_id: UUID
