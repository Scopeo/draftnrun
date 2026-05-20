from typing import Optional

from pydantic import BaseModel, Field


class EmailAddress(BaseModel):
    address: str = Field(description="Email address of the attendee.")
    name: Optional[str] = Field(default=None, description="Display name of the attendee.")


class EventAttendee(BaseModel):
    emailAddress: EmailAddress
    type: Optional[str] = Field(
        default="required",
        description="One of: required, optional, resource.",
    )


class EventDateTime(BaseModel):
    dateTime: str = Field(
        description="ISO 8601 datetime string WITHOUT timezone offset, e.g. '2026-03-20T10:00:00.0000000'.",
    )
    timeZone: str = Field(
        default="UTC",
        description="IANA time zone, e.g. 'Europe/Paris' or 'UTC'.",
    )


class ItemBody(BaseModel):
    contentType: str = Field(
        default="text",
        description="Content type: 'text' or 'html'.",
    )
    content: str = Field(default="", description="Body content of the event.")


class Location(BaseModel):
    displayName: Optional[str] = Field(default=None, description="Display name of the location.")


class PatternedRecurrence(BaseModel):
    pattern: dict = Field(description="Recurrence pattern (type, interval, daysOfWeek, etc.).")
    range: dict = Field(description="Recurrence range (type, startDate, endDate, etc.).")


class EventBody(BaseModel):
    """Body for creating or updating an Outlook Calendar event via MS Graph API."""

    subject: Optional[str] = Field(default=None, description="Title of the event.")
    body: Optional[ItemBody] = Field(default=None, description="Body/notes for the event.")
    start: Optional[EventDateTime] = None
    end: Optional[EventDateTime] = None
    location: Optional[Location] = None
    attendees: Optional[list[EventAttendee]] = None
    isOnlineMeeting: Optional[bool] = Field(
        default=None,
        description="Set to true to create a Teams meeting link.",
    )
    onlineMeetingProvider: Optional[str] = Field(
        default=None,
        description="Online meeting provider, e.g. 'teamsForBusiness'.",
    )
    isAllDay: Optional[bool] = Field(default=None, description="Whether this is an all-day event.")
    recurrence: Optional[PatternedRecurrence] = None
    showAs: Optional[str] = Field(
        default=None,
        description="Free/busy status: 'free', 'tentative', 'busy', 'oof', 'workingElsewhere', 'unknown'.",
    )
    importance: Optional[str] = Field(
        default=None,
        description="Importance: 'low', 'normal', 'high'.",
    )
    isReminderOn: Optional[bool] = Field(default=None, description="Whether a reminder is set.")
    reminderMinutesBeforeStart: Optional[int] = Field(
        default=None,
        description="Minutes before event start to trigger the reminder.",
    )
