from ada_backend.database.component_definition_seeding import upsert_categories
import ada_backend.database.models as db
from uuid import UUID


CATEGORY_UUIDS = {
    "trigger": UUID("3312c1ff-a559-4824-a15f-01780a9bf7c2"),
    "action": UUID("2066b69c-c771-4c05-9788-8790a701c4e0"),
    "query": UUID("2cf1a375-4a05-4e36-adef-f0c72e897dbf"),
    "processing": UUID("802ccf36-cb93-4a91-a57a-24e65f2feee4"),
    "logical": UUID("a0d88f3f-12da-4b65-9879-ea89fc280395"),
    "most_used": UUID("b1c2d3e4-f5a6-7b8c-9d0e-1f2a3b4c5d6e"),
}


def seed_categories(session):
    categories = [
        db.Category(
            id=CATEGORY_UUIDS["trigger"],
            name="Trigger",
            description=(
                "A component whose purpose is to to start a run of the workflow. "
                "It can be linked to an external event, a schedule, a condition...\n"
                "Examples:\n"
                "- A file is created.\n"
                "- A message is received.\n"
                "- A timer expires."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["action"],
            name="Action",
            description=(
                "A component that performs an operation that has an effect on the external world.\n"
                "Examples:\n"
                "- Sending an email.\n"
                "- Writing data to a database."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["query"],
            name="Query",
            description=(
                "A component that retrieves information from the external world "
                "or from a data source.\n"
                "Examples:\n"
                "- Fetch all users older than 18.\n"
                "- Get the latest weather data.\n"
                "- Search for files containing a keyword."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["processing"],
            name="Processing",
            description=(
                "A component that transforms the data taken as input. "
                "It can calculate, reformat, clean, filter, join...\n"
                "Examples:\n"
                "- Data filtering.\n"
                "- Converting file formats."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["logical"],
            name="Logical",
            description=(
                "A component that implements the logic of the workflow. "
                "Conditions, loops, switchs...\n"
                "Examples:\n"
                "- 'If-else' block.\n"
                "- Checking if a payment was successful.\n"
                "- Verifying user permissions."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["most_used"],
            name="Most Used",
            description=(
                "Components that are most frequently used in workflows. "
                "These are essential building blocks for many common use cases.\n"
                "Examples:\n"
                "- AI Agent for intelligent task automation.\n"
                "- LLM Call for direct language model interactions."
            ),
        ),
    ]
    upsert_categories(session, categories)
