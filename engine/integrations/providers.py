from enum import StrEnum


class OAuthProvider(StrEnum):
    SLACK = "slack"
    HUBSPOT = "hubspot"
    GMAIL = "google-mail"
