from enum import StrEnum


class OAuthProvider(StrEnum):
    SLACK = "slack"
    HUBSPOT = "hubspot"
    GOOGLE_MAIL = "google-mail"
