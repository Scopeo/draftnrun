from uuid import UUID

import ada_backend.database.models as db
from ada_backend.database.component_definition_seeding import upsert_categories

CATEGORY_UUIDS = {
    "most_used": UUID("b1c2d3e4-f5a6-7b8c-9d0e-1f2a3b4c5d6e"),
    "workflow_logic": UUID("3312c1ff-a559-4824-a15f-01780a9bf7c2"),
    "ai": UUID("2066b69c-c771-4c05-9788-8790a701c4e0"),
    "search_engine": UUID("2cf1a375-4a05-4e36-adef-f0c72e897dbf"),
    "information_retrieval": UUID("802ccf36-cb93-4a91-a57a-24e65f2feee4"),
    "integrations": UUID("a0d88f3f-12da-4b65-9879-ea89fc280395"),
    "messaging": UUID("e1f2a3b4-c5d6-7e8f-9a0b-1c2d3e4f5a6b"),
    "run_code": UUID("c2d3e4f5-a6b7-8c9d-0e1f-2a3b4c5d6e7f"),
    "file_generation": UUID("d3e4f5a6-b7c8-9d0e-1f2a-3b4c5d6e7f8a"),
}


def seed_categories(session):
    categories = [
        db.Category(
            id=CATEGORY_UUIDS["most_used"],
            name="Most Used",
            description="The most frequently used across all workflows",
            icon="tabler-star",
            display_order=0,
        ),
        db.Category(
            id=CATEGORY_UUIDS["ai"],
            name="AI",
            description="Powered by Artificial Intelligence",
            icon="tabler-brain",
            display_order=1,
        ),
        db.Category(
            id=CATEGORY_UUIDS["workflow_logic"],
            name="Workflow Logic",
            description="Control the flow and decision-making in your workflow",
            icon="tabler-git-branch",
            display_order=2,
        ),
        db.Category(
            id=CATEGORY_UUIDS["information_retrieval"],
            name="Information Retrieval",
            description="Retrieve specific information from databases, APIs, etc.",
            icon="tabler-database-search",
            display_order=3,
        ),
        db.Category(
            id=CATEGORY_UUIDS["search_engine"],
            name="Search Engine",
            description="Search specific sources or the internet with natural language",
            icon="tabler-world-search",
            display_order=4,
        ),
        db.Category(
            id=CATEGORY_UUIDS["integrations"],
            name="Integrations",
            description="Connect to external services (with APIs and MCPs)",
            icon="tabler-plug",
            display_order=5,
        ),
        db.Category(
            id=CATEGORY_UUIDS["messaging"],
            name="Messaging",
            description="Send messages, notifications, and communications",
            icon="tabler-mail",
            display_order=6,
        ),
        db.Category(
            id=CATEGORY_UUIDS["run_code"],
            name="Run Code",
            description="Execute custom code and scripts",
            icon="tabler-code",
            display_order=7,
        ),
        db.Category(
            id=CATEGORY_UUIDS["file_generation"],
            name="File Generation",
            description="Create and generate files, documents, and reports",
            icon="tabler-file-plus",
            display_order=8,
        ),
    ]
    upsert_categories(session, categories)
