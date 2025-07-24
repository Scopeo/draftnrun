from ada_backend.database.component_definition_seeding import upsert_categories
import ada_backend.database.models as db
from uuid import UUID


CATEGORY_UUIDS = {
    "trigger": UUID("3312c1ff-a559-4824-a15f-01780a9bf7c2"),
    "action": UUID("2066b69c-c771-4c05-9788-8790a701c4e0"),
    "query": UUID("2cf1a375-4a05-4e36-adef-f0c72e897dbf"),
    "processing": UUID("802ccf36-cb93-4a91-a57a-24e65f2feee4"),
    "logical": UUID("a0d88f3f-12da-4b65-9879-ea89fc280395"),
}


def seed_categories(session):
    categories = [
        db.Category(
            id=CATEGORY_UUIDS["trigger"],
            name="Trigger",
            description=(
                "A component whose purpose is to detect an event or condition and "
                "signal the system to start a process. "
                "It monitors or listens for something to happen.\n"
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
                "A component that performs a specific operation in response to a command."
                "It is an executable, isolated task that changes the system’s "
                "state or interacts with the environment.\n"
                "Examples:\n"
                "- Sending an email.\n"
                "- Writing data to a database."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["query"],
            name="Query",
            description=(
                "A component that retrieves information from a data source, "
                "usually specifying criteria or filters.\n"
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
                "A component that transforms, calculates, or manipulates data to generate "
                "new information or prepare it for other steps."
                "It performs computations and intermediate work on the data.\n"
                "Examples:\n"
                "- Data filtering.\n"
                "- Converting file formats."
            ),
        ),
        db.Category(
            id=CATEGORY_UUIDS["logical"],
            name="Logical",
            description=(
                "A component that evaluates conditions or makes decisions based on rules or inputs. "
                "It controls the flow of the process by introducing logic and branching.\n"
                "Role in the system:\n"
                "- Implements conditional logic or rules.\n"
                "- Helps direct the workflow into different paths.\n"
                "Examples:\n"
                "- 'If-else' block.\n"
                "- Checking if a payment was successful.\n"
                "- Verifying user permissions."
            ),
        ),
    ]
    upsert_categories(session, categories)
