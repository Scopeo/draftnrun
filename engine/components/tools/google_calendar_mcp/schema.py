from typing import Optional

from pydantic import BaseModel, Field, model_validator


class EventDateTime(BaseModel):
    """Start or end of an event, using either dateTime (timed) or date (all-day)."""

    dateTime: Optional[str] = Field(
        default=None,
        description="RFC3339 datetime with timezone offset, e.g. '2026-03-20T10:00:00+01:00'. Use for timed events.",
    )
    date: Optional[str] = Field(
        default=None,
        description="Date in YYYY-MM-DD format, e.g. '2026-03-20'. Use for all-day events.",
    )
    timeZone: Optional[str] = Field(
        default=None,
        description="IANA time zone, e.g. 'Europe/Paris'. Optional; defaults to the calendar's time zone.",
    )

    @model_validator(mode="after")
    def validate_date_fields(self):
        has_datetime = self.dateTime is not None
        has_date = self.date is not None
        if not (has_datetime ^ has_date):
            raise ValueError("Exactly one of 'dateTime' or 'date' must be provided, not both or neither")
        return self


class EventAttendee(BaseModel):
    email: str
    optional: Optional[bool] = None
    responseStatus: Optional[str] = Field(
        default=None,
        description="One of: needsAction, declined, tentative, accepted.",
    )


class ConferenceSolutionKey(BaseModel):
    type: str = Field(
        default="hangoutsMeet",
        description="Conference type. Use 'hangoutsMeet' for Google Meet.",
    )


class CreateConferenceRequest(BaseModel):
    requestId: str = Field(description="Unique client-generated ID for idempotency.")
    conferenceSolutionKey: ConferenceSolutionKey = Field(default_factory=ConferenceSolutionKey)


class ConferenceData(BaseModel):
    createRequest: Optional[CreateConferenceRequest] = None


class ReminderOverride(BaseModel):
    method: str = Field(description="Reminder delivery method: 'email' or 'popup'.")
    minutes: int = Field(description="Minutes before the event start to trigger the reminder.")


class EventReminders(BaseModel):
    useDefault: bool = Field(description="Whether to use the calendar's default reminders.")
    overrides: Optional[list[ReminderOverride]] = Field(
        default=None,
        description="Custom reminders. Only used when useDefault is false.",
    )


class EventBody(BaseModel):
    """Body for creating or updating a Google Calendar event."""

    summary: Optional[str] = Field(default=None, description="Title of the event.")
    description: Optional[str] = Field(default=None, description="Description / notes for the event.")
    location: Optional[str] = Field(default=None, description="Free-form location string.")
    start: Optional[EventDateTime] = None
    end: Optional[EventDateTime] = None
    attendees: Optional[list[EventAttendee]] = None
    conferenceData: Optional[ConferenceData] = Field(
        default=None,
        description="Set to create a Google Meet link. Requires conferenceDataVersion=1.",
    )
    recurrence: Optional[list[str]] = Field(
        default=None,
        description="RRULE strings, e.g. ['RRULE:FREQ=WEEKLY;COUNT=5'].",
    )
    reminders: Optional[EventReminders] = None
