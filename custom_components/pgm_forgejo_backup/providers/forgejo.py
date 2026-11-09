"""Almacenamiento de copias nativas en un repositorio Forgejo por Git y SSH."""

import hashlib
import json
import os
import re
import shlex
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

CHUNK_SIZE = 16 * 1024**2
MAX_SIZE = 8 * 1024**3
META_LIMIT = 64 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
OID = re.compile(r"[0-9a-f]{40,64}")
HOST = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}")


class ForgejoError(Exception):
    """Error del proveedor con mensaje apto para mostrar."""


class MissingBackup(ForgejoError):
    """No existe la copia solicitada."""


def ssh_address(url):
    """Acepta la URL SSH explícita del botón Clonar de Forgejo."""
    try:
        parsed = urlsplit(url)
        port = parsed.port if parsed.port is not None else 22
        if (
            parsed.scheme == "ssh"
            and parsed.hostname
            and HOST.fullmatch(parsed.hostname)
            and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", parsed.username or "")
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", parsed.path)
            and all(part not in {".", ".."} for part in parsed.path.split("/"))
            and re.fullmatch(r"[\x21-\x7e]+", url)
            and 1 <= port <= 65535
        ):
            return parsed.hostname, port
    except ValueError:
        pass
    raise ForgejoError("Usa una URL ssh://usuario@servidor:puerto/propietario/repositorio.git.")


def _run(args, *, env=None, data=None, timeout=900):
    try:
        return subprocess.run(
            args, input=data, capture_output=True, env=env, timeout=timeout, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ForgejoError(
            "Falló Git o SSH. Comprueba el servidor, la huella y los permisos."
        ) from exc


def generate_key():
    """Genera una identidad Ed25519 dedicada al repositorio de copias."""
    with TemporaryDirectory(prefix="pgm-key-") as folder:
        key = Path(folder) / "identity"
        _run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "pgm-forgejo-backup",
                "-f",
                str(key),
            ]
        )
        return key.read_text(), key.with_suffix(".pub").read_text().strip()


def scan_host(url):
    """La huella obtenida se debe verificar por otro canal antes de conectar."""
    host, port = ssh_address(url)
    output = _run(
        ["ssh-keyscan", "-T", "5", "-t", "ed25519,ecdsa,rsa", "-p", str(port), host],
        timeout=12,
    )
    host_field = host if port == 22 else f"[{host}]:{port}"
    candidates = {}
    for line in output.splitlines():
        if not line or line.startswith(b"#"):
            continue
        _, algorithm, key = line.decode().split()
        fingerprint = _run(["ssh-keygen", "-lf", "-"], data=line + b"\n").decode().split()[1]
        candidates[fingerprint] = f"{host_field} {algorithm} {key}\n"
    if not candidates:
        raise ForgejoError("No se pudo obtener una huella SSH del servidor.")
    return candidates


class Forgejo:
    """Cada copia tiene referencias propias y una ficha ligera para el inventario."""

    def __init__(self, url, private_key, known_host):
        ssh_address(url)
        self.url = url
        self.private_key = private_key
        self.known_host = known_host

    @contextmanager
    def _session(self):
        with TemporaryDirectory(prefix="pgm-forgejo-") as folder:
            root = Path(folder)
            identity = root / "identity"
            known = root / "known_hosts"
            for path, content in ((identity, self.private_key), (known, self.known_host)):
                path.touch(mode=0o600)
                path.write_text(content)
            # Conserva el aislamiento SSH del gestor y evita usar identidades del sistema.
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("GIT_") and key != "SSH_AUTH_SOCK"
            }
            env.update(
                HOME=folder,
                LC_ALL="C",
                GIT_CONFIG_NOSYSTEM="1",
                GIT_CONFIG_GLOBAL="/dev/null",
                GIT_TERMINAL_PROMPT="0",
                GIT_ALLOW_PROTOCOL="ssh",
                GIT_AUTHOR_NAME="Private Git Manager",
                GIT_AUTHOR_EMAIL="backup@localhost",
                GIT_COMMITTER_NAME="Private Git Manager",
                GIT_COMMITTER_EMAIL="backup@localhost",
                GIT_SSH_COMMAND=shlex.join(
                    [
                        "ssh",
                        "-F",
                        "/dev/null",
                        "-i",
                        str(identity),
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "IdentitiesOnly=yes",
                        "-o",
                        "IdentityAgent=none",
                        "-o",
                        "StrictHostKeyChecking=yes",
                        "-o",
                        f"UserKnownHostsFile={known}",
                        "-o",
                        "GlobalKnownHostsFile=/dev/null",
                        "-o",
                        "UpdateHostKeys=no",
                        "-o",
                        "ConnectTimeout=15",
                        "-o",
                        "ServerAliveInterval=15",
                        "-o",
                        "ServerAliveCountMax=3",
                    ]
                ),
            )
            repo = root / "store"

            def git(*args, data=None):
                return _run(["git", "--git-dir", str(repo), *args], env=env, data=data)

            git("init", "--bare", "--quiet")
            yield git

    @staticmethod
    def _refs(backup_id):
        if not isinstance(backup_id, str) or not ID.fullmatch(backup_id):
            raise ForgejoError("Identificador de copia no válido.")
        return tuple(f"refs/tags/pgm-{kind}-{backup_id}" for kind in ("meta", "data"))

    def _remote_refs(self, git, *patterns):
        data = git("ls-remote", "--refs", self.url, *patterns)
        return {
            ref: oid
            for oid, ref in (line.split("\t", 1) for line in data.decode().splitlines())
            if OID.fullmatch(oid)
        }

    def check(self):
        """Comprueba lectura y escritura con una simulación de push sin publicar archivos."""
        with self._session() as git:
            git("ls-remote", self.url)
            blob = self._blob(git, b"probe")
            commit = self._commit(git, [(blob, "probe")])
            git("push", "--dry-run", self.url, f"{commit}:refs/tags/pgm-connection-check")

    @staticmethod
    def _blob(git, data):
        return git("hash-object", "-w", "--stdin", data=data).decode().strip()

    @staticmethod
    def _commit(git, files):
        rows = "".join(f"100644 blob {oid}\t{name}\n" for oid, name in files)
        tree = git("mktree", data=rows.encode()).decode().strip()
        return git("commit-tree", tree, "-m", "Home Assistant backup").decode().strip()

    def upload(self, source, metadata):
        if metadata.get("protected") is not True:
            raise ForgejoError("Forgejo solo acepta copias con cifrado nativo.")
        meta, data = self._refs(metadata["backup_id"])
        size = metadata["size"]
        if not isinstance(size, int) or not 0 < size <= MAX_SIZE:
            raise ForgejoError("La copia supera el límite de 8 GiB o está vacía.")
        with self._session() as git:
            remote = self._remote_refs(git, meta, data)
            digest = hashlib.sha256()
            files = []
            sent = 0
            with source.open("rb") as stream:
                while block := stream.read(CHUNK_SIZE):
                    sent += len(block)
                    if sent > size:
                        raise ForgejoError("El tamaño de la copia no coincide.")
                    digest.update(block)
                    if not remote:
                        files.append((self._blob(git, block), f"part-{len(files):06d}"))
            if sent != size:
                raise ForgejoError("El tamaño de la copia no coincide.")
            record = {"backup": metadata, "sha256": digest.hexdigest()}
            if remote:
                if len(remote) == 2 and self._read_record(git, meta, remote[meta]) == record:
                    return
                raise ForgejoError("Ya existe una copia diferente con el mismo identificador.")
            raw = json.dumps(record, ensure_ascii=True).encode()
            if len(raw) > META_LIMIT:
                raise ForgejoError("Los metadatos de la copia superan el límite.")
            meta_commit = self._commit(git, [(self._blob(git, raw), "metadata.json")])
            data_commit = self._commit(git, files)
            # El alta es atómica y las referencias solo pueden crearse si todavía no existen.
            git(
                "push",
                "--atomic",
                f"--force-with-lease={meta}:",
                f"--force-with-lease={data}:",
                self.url,
                f"{meta_commit}:{meta}",
                f"{data_commit}:{data}",
            )

    def _read_record(self, git, ref, oid):
        git("fetch", "--no-tags", "--depth=1", self.url, ref)
        if git("rev-parse", "FETCH_HEAD").decode().strip() != oid:
            raise ForgejoError("El catálogo cambió durante la lectura. Vuelve a intentarlo.")
        return self._parse_record(git, oid, ref.removeprefix("refs/tags/pgm-meta-"))

    @staticmethod
    def _parse_record(git, oid, backup_id):
        try:
            path = f"{oid}:metadata.json"
            if int(git("cat-file", "-s", path)) > META_LIMIT:
                raise ValueError
            record = json.loads(git("show", path))
            backup = record["backup"]
            if (
                backup["backup_id"] != backup_id
                or backup["protected"] is not True
                or type(backup["size"]) is not int
                or not 0 < backup["size"] <= MAX_SIZE
                or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            ):
                raise ValueError
            return record
        except (TypeError, ValueError, KeyError) as exc:
            raise ForgejoError("Metadatos de copia inválidos en Forgejo.") from exc

    def list(self):
        with self._session() as git:
            remote = self._remote_refs(git, "refs/tags/pgm-meta-*", "refs/tags/pgm-data-*")
            refs = []
            for ref, oid in remote.items():
                backup_id = ref.removeprefix("refs/tags/pgm-meta-")
                if ID.fullmatch(backup_id) and self._refs(backup_id)[1] in remote:
                    refs.append((backup_id, ref, oid))
            if not refs:
                return []
            git(
                "fetch", "--no-tags", "--depth=1", self.url, *(f"{ref}:{ref}" for _, ref, _ in refs)
            )
            results = []
            for backup_id, ref, oid in refs:
                if git("rev-parse", ref).decode().strip() != oid:
                    raise ForgejoError(
                        "El catálogo cambió durante la lectura. Vuelve a intentarlo."
                    )
                results.append(self._parse_record(git, oid, backup_id)["backup"])
            return results

    def _lookup(self, git, backup_id):
        meta, data = self._refs(backup_id)
        remote = self._remote_refs(git, meta, data)
        if len(remote) != 2:
            raise MissingBackup("No existe la copia solicitada.")
        return meta, data, remote

    def get(self, backup_id):
        with self._session() as git:
            meta, _, remote = self._lookup(git, backup_id)
            return self._read_record(git, meta, remote[meta])["backup"]

    def download(self, backup_id, destination):
        with self._session() as git:
            meta, data, remote = self._lookup(git, backup_id)
            record = self._read_record(git, meta, remote[meta])
            git("fetch", "--no-tags", "--depth=1", self.url, data)
            if git("rev-parse", "FETCH_HEAD").decode().strip() != remote[data]:
                raise ForgejoError("La copia cambió durante la descarga.")
            size = record["backup"]["size"]
            expected = [f"part-{i:06d}" for i in range((size + CHUNK_SIZE - 1) // CHUNK_SIZE)]
            if git("ls-tree", "--name-only", remote[data]).decode().splitlines() != expected:
                raise ForgejoError("La copia está incompleta.")
            digest = hashlib.sha256()
            with destination.open("wb") as stream:
                for index, name in enumerate(expected):
                    path = f"{remote[data]}:{name}"
                    if int(git("cat-file", "-s", path)) != min(
                        CHUNK_SIZE, size - index * CHUNK_SIZE
                    ):
                        raise ForgejoError("La copia está incompleta.")
                    block = git("cat-file", "blob", path)
                    stream.write(block)
                    digest.update(block)
            if digest.hexdigest() != record["sha256"]:
                raise ForgejoError("La huella SHA-256 de la copia no coincide.")

    def delete(self, backup_id):
        with self._session() as git:
            meta, data, remote = self._lookup(git, backup_id)
            git(
                "push",
                "--atomic",
                f"--force-with-lease={meta}:{remote[meta]}",
                f"--force-with-lease={data}:{remote[data]}",
                self.url,
                f":{meta}",
                f":{data}",
            )
