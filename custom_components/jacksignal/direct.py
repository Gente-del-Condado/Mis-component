"""Authenticated native uploads and audio-only direct playback."""

from pathlib import Path
import shutil
from uuid import uuid4

from homeassistant.components.file_upload import process_uploaded_file

from .dlna_media import inspect_audio
from .media import AUDIO_EXTENSIONS
from .playback import Sound


def copy_upload(hass, file_id):
    """Consume the HA upload in the executor; keep accepted files in My media."""
    with process_uploaded_file(hass, file_id) as uploaded:
        root = hass.config.media_dirs.get("local")
        if not root or uploaded.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError("A local media directory and audio file are required")
        if uploaded.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("Audio file exceeds 100 MB")
        root = Path(root).resolve()
        directory = (root / "jacksignal").resolve()
        if not directory.is_relative_to(root):
            raise ValueError("Invalid upload directory")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (uuid4().hex + uploaded.suffix.lower())
        with target.open("xb") as output:
            try:
                with uploaded.open("rb") as source:
                    shutil.copyfileobj(source, output)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        return Sound(str(target), uploaded.name, local=True)


async def uploaded_audio(hass, file_id):
    sound = await hass.async_add_executor_job(copy_upload, hass, file_id)
    try:
        await inspect_audio(sound)
    except BaseException:
        await hass.async_add_executor_job(Path(sound.source).unlink, True)
        raise
    return sound
