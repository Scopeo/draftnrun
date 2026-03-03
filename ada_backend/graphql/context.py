from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from strawberry.fastapi import BaseContext

from ada_backend.routers.auth_router import get_user_from_supabase_token


class GraphQLContext(BaseContext):
    def __init__(self, request: Request, db: Session):
        super().__init__()
        self.request = request
        self.db = db

    async def get_user_id(self) -> UUID:
        """Extract and validate the user ID from the Authorization header.

        Raises HTTP 401 if the header is missing or the token is invalid.
        """
        auth_header = self.request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing or invalid")
        token = auth_header[len("bearer "):]
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = await get_user_from_supabase_token(credentials)
        return user.id
