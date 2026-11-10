"""Adjuntos opcionales de Forgejo para descargar el TAR original desde la web."""

import json
import secrets
from http import HTTPStatus
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

FILE_NAME = "backup.tar"
MARKER = "pgm-backup-sha256: "


class ReleaseError(Exception):
    """Error de la API apto para registrar sin mostrar la credencial."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class SSORequired(ReleaseError):
    """YunoHost exige una sesión de navegador antes de llegar a la API."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Un proxy mal configurado no debe reenviar el token ni el archivo a otro servidor.
        return None


def validate_web_url(web_url, ssh_url):
    try:
        web = urlsplit(web_url)
        ssh_path = unquote(urlsplit(ssh_url).path).strip("/").removesuffix(".git")
        web_path = unquote(web.path).rstrip("/").removesuffix(".git")
        web_parts = web_path.removeprefix("/").split("/")
        ssh_parts = ssh_path.split("/")
        if (
            web.scheme == "https"
            and web.hostname
            and web.port != 0
            and not web.username
            and not web.password
            and not web.query
            and not web.fragment
            and len(ssh_parts) == 2
            and len(web_parts) >= 2
            and all(part and part not in {".", ".."} for part in web_parts)
            and [part.lower() for part in web_parts[-2:]] == [part.lower() for part in ssh_parts]
        ):
            return urlunsplit(("https", web.netloc, quote(web_path, safe="/"), "", ""))
    except ValueError:
        pass
    raise ReleaseError("Usa la URL HTTPS del mismo repositorio de copias.")


class Releases:
    provider_name = "Forgejo"

    def __init__(self, web_url, token):
        instance, owner, repo = web_url.rstrip("/").rsplit("/", 2)
        self.repo = f"{instance}/api/v1/repos/{owner}/{repo}"
        self.token = token
        self.opener = build_opener(_NoRedirect)

    def _request(self, method, path="", *, body=None, headers=None, missing=False, base=None):
        request = Request(
            (base or self.repo) + path,
            method=method,
            data=body,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/json",
                **(headers or {}),
            },
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ReleaseError(f"La respuesta de {self.provider_name} es demasiado grande.")
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            location = exc.headers.get("Location", "")
            if 300 <= exc.code < 400 and urlsplit(location).path.rstrip("/") == "/yunohost/sso":
                raise SSORequired(
                    "YunoHost redirige la API de Forgejo al inicio de sesión."
                ) from None
            if missing and exc.code == HTTPStatus.NOT_FOUND:
                return None
            raise ReleaseError(
                f"{self.provider_name} respondió HTTP {exc.code} al gestionar el adjunto.", exc.code
            ) from None
        except (OSError, URLError, ValueError):
            raise ReleaseError(
                f"No se pudo gestionar el adjunto en {self.provider_name}."
            ) from None

    def check(self):
        info = self._request("GET")
        if not isinstance(info, dict) or info.get("private") is not True:
            raise ReleaseError("El destino de las copias debe ser privado.")
        if not (info.get("permissions") or {}).get("push"):
            raise ReleaseError("El token necesita acceso de escritura al repositorio de copias.")

    @staticmethod
    def _tag(backup_id):
        return "pgm-data-" + quote(backup_id, safe="")

    def _release(self, backup_id):
        return self._request("GET", "/releases/tags/" + self._tag(backup_id), missing=True)

    @staticmethod
    def _managed(release, digest):
        return isinstance(release, dict) and release.get("body") == MARKER + digest

    def available(self, backup_id, size):
        release = self._release(backup_id)
        return bool(
            isinstance(release, dict)
            and str(release.get("body", "")).startswith(MARKER)
            and any(
                a.get("name") == FILE_NAME and a.get("size") == size
                for a in release.get("assets", [])
            )
        )

    def upload(self, backup_id, source, size, digest):
        self.check()
        release = self._release(backup_id)
        if release is None:
            tag = self._tag(backup_id)
            for attempt in range(3):
                try:
                    release = self._request(
                        "POST",
                        "/releases",
                        body=json.dumps(
                            {
                                "tag_name": tag,
                                "name": f"Copia cifrada {backup_id}",
                                "body": MARKER + digest,
                            }
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    break
                except ReleaseError as exc:
                    release = self._release(backup_id)
                    if release is not None:
                        break
                    # Forgejo puede tardar en registrar la primera rama después del push SSH.
                    if exc.status != HTTPStatus.UNPROCESSABLE_ENTITY or attempt == 2:
                        raise
                    sleep(attempt + 1)
        if not self._managed(release, digest):
            raise ReleaseError("Ya existe un lanzamiento distinto para esta copia.")
        for asset in release.get("assets", []):
            if asset.get("name") == FILE_NAME:
                if asset.get("size") == size:
                    return
                raise ReleaseError("El adjunto existente tiene un tamaño diferente.")

        try:
            self._upload_asset(int(release["id"]), source, size)
        except ReleaseError:
            if not self.available(backup_id, size):
                raise

    def _upload_asset(self, release_id, source, size):
        # Envía el TAR como flujo con longitud conocida, sin cargar la copia completa en memoria.
        boundary = secrets.token_hex(16)
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="attachment"; filename="{FILE_NAME}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()

        def chunks():
            yield prefix
            with source.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    yield block
            yield suffix

        self._request(
            "POST",
            f"/releases/{release_id}/assets?name={FILE_NAME}",
            body=chunks(),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(prefix) + size + len(suffix)),
            },
        )

    @staticmethod
    def _asset_path(release_id, asset_id):
        return f"/releases/{release_id}/assets/{asset_id}"

    def delete(self, backup_id, digest):
        release = self._release(backup_id)
        if not self._managed(release, digest):
            return
        release_path = f"/releases/{int(release['id'])}"
        assets = release.get("assets", [])
        if all(asset.get("name") == FILE_NAME for asset in assets):
            self._request("DELETE", release_path, missing=True)
        else:
            # El propietario puede añadir adjuntos propios al lanzamiento.
            for asset in assets:
                if asset.get("name") == FILE_NAME:
                    self._request(
                        "DELETE",
                        self._asset_path(int(release["id"]), int(asset["id"])),
                        missing=True,
                    )
