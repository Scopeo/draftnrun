import secrets
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from settings import settings

_MAX_AGE_SECONDS = 30 * 60


def _get_serializer() -> URLSafeTimedSerializer:
    if not settings.BACKEND_SECRET_KEY:
        raise RuntimeError("BACKEND_SECRET_KEY is required for GitHub install state tokens")
    return URLSafeTimedSerializer(settings.BACKEND_SECRET_KEY, salt="github-install-state")


def create_install_state(org_id: UUID, user_id: UUID) -> str:
    s = _get_serializer()
    return s.dumps({"org": str(org_id), "uid": str(user_id), "n": secrets.token_hex(16)})


def verify_install_state(state: str, org_id: UUID, user_id: UUID) -> None:
    """Validate a signed install state token.

    Raises ValueError if the token is invalid, expired, or does not match
    the supplied org_id / user_id.
    """
    s = _get_serializer()
    try:
        data = s.loads(state, max_age=_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise ValueError("GitHub install state has expired") from exc
    except BadSignature as exc:
        raise ValueError("Invalid GitHub install state") from exc
    if data.get("org") != str(org_id) or data.get("uid") != str(user_id):
        raise ValueError("GitHub install state does not match caller")
