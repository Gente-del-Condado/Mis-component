"""Agente nativo. Home Assistant cifra, programa y restaura cada copia."""

import asyncio
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from homeassistant.components.backup import (
    AgentBackup,
    BackupAgent,
    BackupAgentError,
    BackupNotFound,
)
from homeassistant.core import callback

from . import DOMAIN, LISTENERS
from .providers.forgejo import MAX_SIZE, Forgejo, ForgejoError, MissingBackup
from .providers.forgejo_releases import Releases


async def async_get_backup_agents(hass, **kwargs):
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if hasattr(entry, "runtime_data")
    ]


@callback
def async_register_backup_agents_listener(hass, *, listener, **kwargs):
    listeners = hass.data.setdefault(LISTENERS, [])
    listeners.append(listener)
    return lambda: listeners.remove(listener)


class ForgejoBackupAgent(BackupAgent):
    domain = DOMAIN

    def __init__(self, hass, entry):
        super().__init__()
        self.hass = hass
        self.name = entry.title
        self.unique_id = entry.entry_id
        options = entry.options
        releases = (
            Releases(options["web_url"], options["release_token"])
            if options.get("web_url")
            else None
        )
        self.provider = Forgejo(
            entry.data["url"],
            entry.data["identity"],
            entry.data["known_host"],
            releases,
            time_zone=hass.config.time_zone,
        )

    async def _call(self, function, *args):
        job = self.hass.async_add_executor_job(function, *args)
        try:
            return await asyncio.shield(job)
        except asyncio.CancelledError:
            # Git puede seguir leyendo el temporal tras la cancelación de la petición.
            await asyncio.gather(job, return_exceptions=True)
            raise
        except MissingBackup as exc:
            raise BackupNotFound(str(exc)) from exc
        except ForgejoError as exc:
            raise BackupAgentError(str(exc)) from exc

    @asynccontextmanager
    async def _temporary_archive(self):
        # La creación y el borrado recursivo pueden bloquear el bucle de Core.
        directory = await self._call(TemporaryDirectory, None, "pgm-ha-")
        try:
            yield Path(directory.name) / "backup.tar"
        finally:
            await self._call(directory.cleanup)

    @staticmethod
    def _metadata(data):
        try:
            return AgentBackup.from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise BackupAgentError("Los metadatos de Forgejo no son válidos.") from exc

    async def async_list_backups(self, **kwargs):
        return [self._metadata(data) for data in await self._call(self.provider.list)]

    async def async_get_backup(self, backup_id, **kwargs):
        return self._metadata(await self._call(self.provider.get, backup_id))

    async def async_delete_backup(self, backup_id, **kwargs):
        await self._call(self.provider.delete, backup_id)

    async def async_upload_backup(self, *, open_stream, backup, on_progress, **kwargs):
        # Verifica antes de abrir el flujo. La contraseña y las claves de cifrado siguen en Core.
        if backup.protected is not True:
            raise BackupAgentError("Activa el cifrado para esta ubicación en Home Assistant.")
        if not 0 < backup.size <= MAX_SIZE:
            raise BackupAgentError("El tamaño de la copia supera el límite de 8 GiB o está vacío.")
        async with self._temporary_archive() as path:
            try:
                size = 0
                target = await self._call(path.open, "wb")
                try:
                    async with aclosing(await open_stream()) as source:
                        async for chunk in source:
                            size += len(chunk)
                            if size > backup.size:
                                raise BackupAgentError("El tamaño de la copia no coincide.")
                            await self._call(target.write, chunk)
                finally:
                    await self._call(target.close)
                await self._call(self.provider.upload, path, backup.as_dict())
            except OSError as exc:
                raise BackupAgentError(
                    "No se pudo preparar el archivo temporal de la copia."
                ) from exc
        on_progress(bytes_uploaded=backup.size)

    async def async_download_backup(self, backup_id, **kwargs):
        # Haz visible una copia ausente antes de que Core empiece a consumir el archivo.
        await self._call(self.provider.get, backup_id)

        async def stream():
            async with self._temporary_archive() as path:
                try:
                    await self._call(self.provider.download, backup_id, path)
                    source = await self._call(path.open, "rb")
                    try:
                        while chunk := await self._call(source.read, 1024 * 1024):
                            yield chunk
                    finally:
                        await self._call(source.close)
                except OSError as exc:
                    raise BackupAgentError("No se pudo preparar la descarga temporal.") from exc

        return stream()
