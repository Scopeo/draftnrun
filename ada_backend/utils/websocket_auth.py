import urllib.parse

from fastapi import WebSocket


def get_bearer_token_from_websocket(websocket: WebSocket) -> str | None:
    headers = websocket.scope.get("headers") or []
    for name, value in headers:
        if name.lower() == b"authorization" and value.lower().startswith(b"bearer "):
            return value[7:].decode().strip()
    query_string = websocket.scope.get("query_string", b"").decode()
    params = urllib.parse.parse_qs(query_string)
    token_list = params.get("token") or params.get("authorization") or []
    token = token_list[0] if token_list else None
    if token and token.lower().startswith("bearer "):
        return token[7:].strip()
    return token if token else None
