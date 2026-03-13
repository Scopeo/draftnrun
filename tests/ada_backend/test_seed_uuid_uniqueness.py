from collections import defaultdict
from uuid import UUID

import pytest

from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS
from ada_backend.database.seed.seed_ai_agent import AI_MODEL_PARAMETER_IDS, PARAMETER_GROUP_UUIDS
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_llm_call import (
    LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID,
    LLM_CALL_PARAMETER_GROUP_UUIDS,
    LLM_CALL_PARAMETER_IDS,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS

ALL_UUID_SOURCES: list[tuple[str, dict[str, UUID]]] = [
    ("COMPONENT_UUIDS", COMPONENT_UUIDS),
    ("COMPONENT_VERSION_UUIDS", COMPONENT_VERSION_UUIDS),
    ("TOOL_DESCRIPTION_UUIDS", TOOL_DESCRIPTION_UUIDS),
    ("LLM_CALL_PARAMETER_IDS", LLM_CALL_PARAMETER_IDS),
    ("LLM_CALL_PARAMETER_GROUP_UUIDS", LLM_CALL_PARAMETER_GROUP_UUIDS),
    ("AI_MODEL_PARAMETER_IDS", AI_MODEL_PARAMETER_IDS),
    ("PARAMETER_GROUP_UUIDS", PARAMETER_GROUP_UUIDS),
    ("CATEGORY_UUIDS", CATEGORY_UUIDS),
    ("INTEGRATION_UUIDS", INTEGRATION_UUIDS),
]

STANDALONE_UUIDS: dict[str, UUID] = {
    "LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID": LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID,
}


def test_all_seed_uuids_are_globally_unique() -> None:
    """Every UUID across all seed files must be unique.

    The only accepted exception is the intentional pattern where a component's
    first version reuses the component's own UUID (component_id == version_id).
    """
    allowed_duplicates = set(COMPONENT_UUIDS.values()) & set(COMPONENT_VERSION_UUIDS.values())

    sources_by_uuid: dict[UUID, list[str]] = defaultdict(list)

    for dict_name, uuid_dict in ALL_UUID_SOURCES:
        for key, val in uuid_dict.items():
            sources_by_uuid[val].append(f"{dict_name}[{key!r}]")

    for name, val in STANDALONE_UUIDS.items():
        sources_by_uuid[val].append(name)

    unexpected_duplicates = {
        uuid_value: sources
        for uuid_value, sources in sources_by_uuid.items()
        if len(sources) > 1 and uuid_value not in allowed_duplicates
    }

    if unexpected_duplicates:
        descriptions = [
            f"{uuid_value}: {', '.join(sorted(sources))}"
            for uuid_value, sources in sorted(unexpected_duplicates.items(), key=str)
        ]
        pytest.fail("Unexpected duplicate UUIDs in seed files: " + "; ".join(descriptions))
