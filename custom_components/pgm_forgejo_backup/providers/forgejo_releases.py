"""Adjuntos opcionales de Forgejo para descargar el TAR original desde la web."""

import json
import secrets
from http import HTTPStatus
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

FILE_NAME = "backup.tar"
MARKER = "pgm-backup-sha256: "


class ReleaseError(Exception):
    """Error de la API apto para registrar sin mostrar la credencial."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Un proxy mal configurado no debe reenviar el token ni el archivo a otro servidor.
        return None


def validate_web_url(web_url, ssh_url):
    try:
        web = urlsplit(web_url)
        ssh_path = unquote(urlsplit(ssh_url).path).strip("/").removesuffix(".git")
        web_path = unquote(web.path).strip("/")
        if (
            web.scheme == "https"
            and web.hostname
            and web.port != 0
            and not web.username
            and not web.password
            and not web.query
            and not web.fragment
            and web_path.split("/")[-2:] == ssh_path.split("/")[-2:]
        ):
            return web_url.rstrip("/")
    except ValueError:
        pass
    raise ReleaseError("Usa la URL HTTPS del mismo repositorio de copias.")


class Releases:
    def __init__(self, web_url, token):
        instance, owner, repo = web_url.rstrip("/").rsplit("/", 2)
        self.repo = f"{instance}/api/v1/repos/{owner}/{repo}"
        self.token = token
        self.opener = build_opener(_NoRedirect)

    def _request(self, method, path="", *, body=None, headers=None, missing=False):
        request = Request(
            self.repo + path,
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
                    raise ReleaseError("La respuesta de Forgejo es demasiado grande.")
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            if missing and exc.code == HTTPStatus.NOT_FOUND:
                return None
            raise ReleaseError(
                f"Forgejo respondió HTTP {exc.code} al gestionar el adjunto.", exc.code
            ) from None
        except (OSError, URLError, ValueError):
            raise ReleaseError("No se pudo gestionar el adjunto en Forgejo.") from None

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

        release_id = int(release["id"])
        try:
            self._request(
                "POST",
                f"/releases/{release_id}/assets?name={FILE_NAME}",
                body=chunks(),
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(prefix) + size + len(suffix)),
                },
            )
        except ReleaseError:
            if not self.available(backup_id, size):
                raise

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
                        "DELETE", f"{release_path}/assets/{int(asset['id'])}", missing=True
                    )
