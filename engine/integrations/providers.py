from enum import StrEnum


class OAuthProvider(StrEnum):
    SLACK = "slack"
    HUBSPOT = "hubspot"
    HUBSPOT_NEVERDROP = "hubspot-neverdrop"
    NOTION = "notion"
    NOTION_NEVERDROP = "notion-neverdrop"
    GMAIL = "google-mail"
    GMAIL_NEVERDROP = "google-mail-neverdrop"
    GOOGLE_CALENDAR = "google-calendar"
    GOOGLE_CALENDAR_NEVERDROP = "google-calendar-neverdrop"
    GOOGLE_CONTACT_NEVERDROP = "google-contact-neverdrop"
    OUTLOOK = "outlook"
    OUTLOOK_CALENDAR = "outlook-calendar"
