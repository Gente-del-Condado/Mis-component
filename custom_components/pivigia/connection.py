"""Validación de conexión compartida por el alta, reconfiguración y consulta de estado."""

from urllib.parse import urlsplit


def normalize_url(value):
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError("invalid_url")
    _ = parsed.port
    return value


async def fetch_status(session, url, token):
    url = normalize_url(url)
    async with session.get(url + "/api/status", headers={"Authorization": "Bearer " + token},
                           timeout=10, allow_redirects=False) as response:
        if response.status in {401, 403}:
            raise PermissionError("invalid_auth")
        if response.status != 200:
            raise ConnectionError("cannot_connect")
        data = await response.json()
    if not isinstance(data, dict) or data.get("name") != "PiVigia" or not isinstance(data.get("counts"), dict):
        raise ValueError("invalid_response")
    return data
