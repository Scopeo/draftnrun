from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared Pydantic models
# ---------------------------------------------------------------------------


class AssocType(BaseModel):
    associationCategory: str
    associationTypeId: int


class AssocTarget(BaseModel):
    id: str


class Association(BaseModel):
    to: AssocTarget
    types: list[AssocType]


class FilterOperator(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    BETWEEN = "BETWEEN"
    IN = "IN"
    NOT_IN = "NOT_IN"
    HAS_PROPERTY = "HAS_PROPERTY"
    NOT_HAS_PROPERTY = "NOT_HAS_PROPERTY"
    CONTAINS_TOKEN = "CONTAINS_TOKEN"
    NOT_CONTAINS_TOKEN = "NOT_CONTAINS_TOKEN"


class SearchFilter(BaseModel):
    propertyName: str
    operator: FilterOperator
    value: Optional[Any] = None


class FilterGroup(BaseModel):
    filters: list[SearchFilter]


# ---------------------------------------------------------------------------
# Contact property models
# ---------------------------------------------------------------------------


class ContactProperties(BaseModel):
    model_config = ConfigDict(extra="allow")

    email: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    phone: Optional[str] = None
    mobilephone: Optional[str] = None
    company: Optional[str] = None
    jobtitle: Optional[str] = None
    lifecyclestage: Optional[
        Literal[
            "subscriber",
            "lead",
            "marketingqualifiedlead",
            "salesqualifiedlead",
            "opportunity",
            "customer",
            "evangelist",
            "other",
        ]
    ] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    hubspot_owner_id: Optional[str] = None


class CompanyProperties(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    domain: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    numberofemployees: Optional[int] = None
    annualrevenue: Optional[float] = None
    lifecyclestage: Optional[Literal["lead", "customer", "opportunity", "subscriber", "other"]] = None
    hubspot_owner_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Engagement property models
# ---------------------------------------------------------------------------


class NoteProperties(BaseModel):
    model_config = ConfigDict(extra="allow")

    hs_note_body: str
    hs_timestamp: str = Field(description="ISO 8601 datetime (e.g. '2026-02-27T10:00:00Z'). Required by HubSpot.")
    hubspot_owner_id: Optional[str] = None


class TaskProperties(BaseModel):
    model_config = ConfigDict(extra="allow")

    hs_task_subject: str
    hs_task_body: str
    hs_timestamp: str = Field(description="ISO 8601 datetime (e.g. '2026-02-27T10:00:00Z'). Required by HubSpot.")
    hs_task_type: Literal["TODO", "EMAIL", "CALL"] = Field(
        default="TODO",
        description="Required by HubSpot despite schema marking it optional.",
    )
    hs_task_due_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 string (e.g. '2026-02-28T09:00:00Z'). Must be a string, not a number.",
    )
    hs_task_status: Optional[Literal["NOT_STARTED", "IN_PROGRESS", "WAITING", "COMPLETED", "DEFERRED"]] = None
    hs_task_priority: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = None
    hubspot_owner_id: Optional[str] = None


class EmailProperties(BaseModel):
    """
    Log an email in HubSpot's engagement timeline (does not send a real email).

    To set sender/recipient use hs_email_headers (JSON string), not
    hs_email_from_email / hs_email_to_email which are read-only computed fields.
    """

    model_config = ConfigDict(extra="allow")

    hs_email_subject: str
    hs_email_text: str
    hs_timestamp: str = Field(description="ISO 8601 datetime (e.g. '2026-02-27T10:00:00Z'). Required by HubSpot.")
    hs_email_headers: Optional[str] = Field(
        default=None,
        description=(
            'JSON string with from/to. Example: \'{"from":{"email":"sender@example.com"},'
            '"to":[{"email":"recipient@example.com"}]}\''
        ),
    )
    hs_email_html: Optional[str] = None
    hs_email_status: Optional[Literal["SENT", "DRAFT", "SCHEDULED"]] = None
    hs_email_direction: Optional[Literal["FORWARDED_EMAIL", "INCOMING_EMAIL", "EMAIL", "DRAFT_EMAIL"]] = None
    hubspot_owner_id: Optional[str] = None
