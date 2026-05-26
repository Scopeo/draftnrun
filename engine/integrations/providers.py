from enum import StrEnum


class OAuthProvider(StrEnum):
    SLACK = "slack"
    HUBSPOT = "hubspot"
    HUBSPOT_NEVERDROP = "hubspot-neverdrop"
    NOTION = "notion"
    NOTION_NEVERDROP = "notion-neverdrop"
    GMAIL = "google-mail"
    GOOGLE_CALENDAR = "google-calendar"
    OUTLOOK = "outlook"
    OUTLOOK_CALENDAR = "outlook-calendar"
