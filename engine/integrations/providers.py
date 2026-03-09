from enum import StrEnum


class OAuthProvider(StrEnum):
    SLACK = "slack"
    HUBSPOT = "hubspot"
    HUBSPOT_NEVERDROP = "hubspot-neverdrop"
    GMAIL = "google-mail"
    OUTLOOK = "microsoft-mail"
